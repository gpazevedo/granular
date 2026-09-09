"""Tests for AdvisoryService and the readiness/unlock endpoints using a fake graph."""

from __future__ import annotations

from fastapi.testclient import TestClient

from granular.api.dependencies import get_advisory_service
from granular.api.main import create_app
from granular.api.services.advisory_service import AdvisoryService


class FakeGraph:
    def __init__(self, prereqs=None, unlocks=None, existing=None) -> None:
        # prereqs: {course_id: [{"course_id","title","verbatim"}, ...]}
        self._prereqs = prereqs or {}
        # unlocks: {course_id: [{"course_id","title"}, ...]}
        self._unlocks = unlocks or {}
        # existing: set of known course ids (defaults to keys of the two maps)
        self._existing = existing if existing is not None else (
            set(self._prereqs) | set(self._unlocks)
        )

    def course_exists(self, course_id: str) -> bool:
        return course_id in self._existing

    def get_prerequisites(self, course_id: str):
        return self._prereqs.get(course_id, [])

    def get_unlocks(self, course_id: str):
        return self._unlocks.get(course_id, [])


def _client(graph: FakeGraph) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_advisory_service] = lambda: AdvisoryService(graph)
    return TestClient(app)


# --- Readiness ---------------------------------------------------------------

class TestReadiness:
    def test_all_prereqs_met_is_ready(self):
        graph = FakeGraph(
            prereqs={"CS-2": [{"course_id": "CS-1", "title": "Intro", "verbatim": "Prereq: CS-1"}]}
        )
        svc = AdvisoryService(graph)
        r = svc.readiness("CS-2", completed_courses=["CS-1"])
        assert r.ready is True
        assert r.unmet_prerequisites == []
        assert r.evidence_basis == "declared"

    def test_unmet_prereq_returned_with_verbatim(self):
        graph = FakeGraph(
            prereqs={"CS-2": [{"course_id": "CS-1", "title": "Intro", "verbatim": "Prereq: CS-1"}]}
        )
        svc = AdvisoryService(graph)
        r = svc.readiness("CS-2", completed_courses=[])
        assert r.ready is False
        assert len(r.unmet_prerequisites) == 1
        assert r.unmet_prerequisites[0].course_id == "CS-1"
        assert r.unmet_prerequisites[0].verbatim == "Prereq: CS-1"

    def test_partial_completion(self):
        graph = FakeGraph(
            prereqs={
                "CS-3": [
                    {"course_id": "CS-1", "title": "A", "verbatim": ""},
                    {"course_id": "CS-2", "title": "B", "verbatim": ""},
                ]
            }
        )
        svc = AdvisoryService(graph)
        r = svc.readiness("CS-3", completed_courses=["CS-1"])
        assert r.ready is False
        assert [p.course_id for p in r.unmet_prerequisites] == ["CS-2"]

    def test_course_not_found(self):
        svc = AdvisoryService(FakeGraph(existing=set()))
        r = svc.readiness("CS-999", completed_courses=[])
        assert r.status == "course_not_found"
        assert r.ready is False

    def test_no_prereqs_is_ready(self):
        graph = FakeGraph(prereqs={"CS-1": []}, existing={"CS-1"})
        r = AdvisoryService(graph).readiness("CS-1", completed_courses=[])
        assert r.ready is True


# --- Unlock ------------------------------------------------------------------

class TestUnlock:
    def test_unlocks_returned(self):
        graph = FakeGraph(
            unlocks={"CS-1": [{"course_id": "CS-2", "title": "Next"}]}, existing={"CS-1"}
        )
        r = AdvisoryService(graph).unlock("CS-1")
        assert r.evidence_basis == "declared"
        assert [u.course_id for u in r.unlocks] == ["CS-2"]

    def test_course_not_found(self):
        r = AdvisoryService(FakeGraph(existing=set())).unlock("CS-999")
        assert r.status == "course_not_found"
        assert r.unlocks == []


# --- Endpoints ---------------------------------------------------------------

class TestEndpoints:
    def test_readiness_endpoint(self):
        graph = FakeGraph(
            prereqs={"CS-2": [{"course_id": "CS-1", "title": "Intro", "verbatim": "Prereq: CS-1"}]}
        )
        client = _client(graph)
        resp = client.post("/api/v1/readiness", json={"course_id": "CS-2", "completed_courses": []})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ready"] is False
        assert body["evidence_basis"] == "declared"

    def test_readiness_empty_course_id_rejected(self):
        client = _client(FakeGraph())
        resp = client.post("/api/v1/readiness", json={"course_id": "", "completed_courses": []})
        assert resp.status_code in (400, 422)

    def test_unlock_endpoint(self):
        graph = FakeGraph(unlocks={"CS-1": [{"course_id": "CS-2", "title": "Next"}]}, existing={"CS-1"})
        client = _client(graph)
        resp = client.get("/api/v1/unlock/CS-1")
        assert resp.status_code == 200
        assert resp.json()["unlocks"][0]["course_id"] == "CS-2"
