"""Tests for AdvisoryService and the readiness/unlock endpoints using a fake graph."""

from __future__ import annotations

from fastapi.testclient import TestClient

from granular.api.dependencies import get_advisory_service
from granular.api.main import create_app
from granular.api.services.advisory_service import AdvisoryService


class FakeGraph:
    def __init__(self, prereqs=None, unlocks=None, existing=None, concepts=None, covered=None, details=None) -> None:
        # prereqs: {course_id: [{"course_id","title","verbatim"}, ...]}
        self._prereqs = prereqs or {}
        # unlocks: {course_id: [{"course_id","title"}, ...]}
        self._unlocks = unlocks or {}
        # concepts: {course_id: [{"ku_id","ku_label","knowledge_area","confidence"}, ...]}
        self._concepts = concepts or {}
        # covered: {course_id: {ku_id, ...}} — KUs a completed course covers
        self._covered = covered or {}
        # details: {course_id: {course node fields + "concepts": [...]}}
        self._details = details or {}
        # existing: set of known course ids (defaults to keys of the maps)
        self._existing = existing if existing is not None else (
            set(self._prereqs) | set(self._unlocks) | set(self._concepts) | set(self._details)
        )

    def course_exists(self, course_id: str) -> bool:
        return course_id in self._existing

    def get_prerequisites(self, course_id: str):
        return self._prereqs.get(course_id, [])

    def get_unlocks(self, course_id: str):
        return self._unlocks.get(course_id, [])

    def course_concepts(self, course_id: str):
        return self._concepts.get(course_id, [])

    def covered_ku_ids(self, course_ids):
        result = set()
        for c in course_ids:
            result |= self._covered.get(c, set())
        return result

    def course_detail(self, course_id: str):
        return self._details.get(course_id)


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


# --- Overlap -----------------------------------------------------------------

class TestOverlap:
    def _graph(self):
        # Target CS-3 covers KU-A, KU-B, KU-C. CS-1 covers KU-A; CS-2 covers KU-B.
        return FakeGraph(
            concepts={
                "CS-3": [
                    {"ku_id": "KU-A", "ku_label": "A", "knowledge_area": "AL", "confidence": 0.8},
                    {"ku_id": "KU-B", "ku_label": "B", "knowledge_area": "DS", "confidence": 0.6},
                    {"ku_id": "KU-C", "ku_label": "C", "knowledge_area": "OS", "confidence": 0.7},
                ]
            },
            covered={"CS-1": {"KU-A"}, "CS-2": {"KU-B"}},
            existing={"CS-1", "CS-2", "CS-3"},
        )

    def test_matched_and_gap_split(self):
        r = AdvisoryService(self._graph()).overlap("CS-3", ["CS-1", "CS-2"])
        matched = {c.ku_id for c in r.matched_concepts}
        gaps = {c.ku_id for c in r.gap_concepts}
        assert matched == {"KU-A", "KU-B"}
        assert gaps == {"KU-C"}
        assert r.evidence_basis == "inferred"

    def test_confidence_is_mean_of_matched(self):
        r = AdvisoryService(self._graph()).overlap("CS-3", ["CS-1", "CS-2"])
        # matched KU-A (0.8) and KU-B (0.6) -> mean 0.7
        assert r.confidence == 0.7

    def test_no_completed_all_gaps(self):
        r = AdvisoryService(self._graph()).overlap("CS-3", [])
        assert r.matched_concepts == []
        assert {c.ku_id for c in r.gap_concepts} == {"KU-A", "KU-B", "KU-C"}
        assert r.confidence == 0.0

    def test_caveat_is_non_entitlement(self):
        r = AdvisoryService(self._graph()).overlap("CS-3", ["CS-1"])
        # Must not use entitlement language; explicitly disclaims exemption.
        assert "exempt" not in r.caveat.lower() or "exemption" in r.caveat.lower()
        assert r.caveat  # non-empty

    def test_course_not_found(self):
        r = AdvisoryService(FakeGraph(existing=set())).overlap("CS-999", [])
        assert r.status == "course_not_found"


# --- Course detail -----------------------------------------------------------

class TestCourseDetail:
    def _graph(self):
        return FakeGraph(
            details={
                "CS-225": {
                    "course_id": "CS-225",
                    "course_number": "225",
                    "subject_code": "CS",
                    "title": "Data Structures",
                    "level": "undergraduate",
                    "description": "Elementary data structures and their implementations.",
                    "concepts": [
                        {"ku_id": "KU-A", "label": "Graphs and Trees", "knowledge_area": "DS", "confidence": 0.72},
                        {"ku_id": "KU-B", "label": "Fundamental Data Structures", "knowledge_area": "SDF", "confidence": 0.59},
                    ],
                }
            },
            prereqs={"CS-225": [{"course_id": "CS-173", "title": "Discrete", "verbatim": "Prereq: CS-173"}]},
            unlocks={"CS-225": [{"course_id": "CS-374", "title": "Algorithms"}]},
        )

    def test_full_detail(self):
        r = AdvisoryService(self._graph()).course_detail("CS-225")
        assert r.status == "ok"
        assert r.title == "Data Structures"
        assert r.description
        assert len(r.concepts) == 2
        # concepts sorted by confidence desc
        assert r.concepts[0].ku_id == "KU-A"
        assert [p.course_id for p in r.prerequisites] == ["CS-173"]
        assert [u.course_id for u in r.unlocks] == ["CS-374"]
        assert r.evidence_basis == "mixed"

    def test_course_not_found(self):
        r = AdvisoryService(FakeGraph()).course_detail("CS-999")
        assert r.status == "course_not_found"
        assert r.concepts == []


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

    def test_course_detail_endpoint(self):
        graph = FakeGraph(
            details={
                "CS-1": {
                    "course_id": "CS-1", "course_number": "1", "subject_code": "CS",
                    "title": "Intro", "level": "undergraduate", "description": "desc",
                    "concepts": [{"ku_id": "KU-A", "label": "A", "knowledge_area": "AL", "confidence": 0.8}],
                }
            },
        )
        client = _client(graph)
        resp = client.get("/api/v1/course/CS-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "Intro"
        assert body["concepts"][0]["ku_id"] == "KU-A"

    def test_overlap_endpoint(self):
        graph = FakeGraph(
            concepts={
                "CS-3": [
                    {"ku_id": "KU-A", "ku_label": "A", "knowledge_area": "AL", "confidence": 0.8},
                    {"ku_id": "KU-C", "ku_label": "C", "knowledge_area": "OS", "confidence": 0.7},
                ]
            },
            covered={"CS-1": {"KU-A"}},
            existing={"CS-1", "CS-3"},
        )
        client = _client(graph)
        resp = client.post("/api/v1/overlap", json={"course_id": "CS-3", "completed_courses": ["CS-1"]})
        assert resp.status_code == 200
        body = resp.json()
        assert body["evidence_basis"] == "inferred"
        assert {c["ku_id"] for c in body["matched_concepts"]} == {"KU-A"}
        assert {c["ku_id"] for c in body["gap_concepts"]} == {"KU-C"}
