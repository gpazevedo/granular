"""Tests for DiscoverService and the /discover endpoint using fakes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from granular.api.config import APIConfig
from granular.api.main import create_app
from granular.api.dependencies import get_discover_service
from granular.api.services.discover_service import DiscoverService
from granular.api.services.matcher import CourseMatch
from granular.api.services.resolver import ResolutionResult


class FakeResolver:
    def __init__(self, ku_ids: list[str]) -> None:
        self._ku_ids = ku_ids

    def resolve(self, query: str) -> ResolutionResult:
        return ResolutionResult(
            ku_ids=self._ku_ids, model_id="fake-model", resolved=len(self._ku_ids) > 0
        )


class FakeGraph:
    def __init__(self, matches=None, thin=None, declared=None, labels=None) -> None:
        self._matches = matches or []
        self._thin = thin or []
        self._declared = declared or set()
        self._labels = labels or {}

    def match_courses(self, ku_ids, level):
        if level == "all":
            return self._matches
        return [m for m in self._matches if m.level == level]

    def declared_prereqs_between(self, course_ids):
        return self._declared

    def thin_coverage_units(self, ku_ids, min_courses):
        return self._thin

    def ku_labels(self, ku_ids):
        return self._labels


def make_match(cid, number, kus, level="undergraduate", relevance=0.8) -> CourseMatch:
    return CourseMatch(
        course_id=cid,
        course_number=number,
        subject_code="CS",
        title=f"Course {number}",
        level=level,
        credits="3",
        description_excerpt="A course about algorithms.",
        covered_ku_ids=list(kus),
        relevance_score=relevance,
    )


def make_service(resolver, graph) -> DiscoverService:
    return DiscoverService(resolver, graph, APIConfig())


class TestDiscoverService:
    def test_no_concepts_resolved(self):
        svc = make_service(FakeResolver([]), FakeGraph())
        resp = svc.discover("gibberish xyzzy", "all")
        assert resp.status == "no_concepts_resolved"
        assert resp.courses == []

    def test_no_courses_found(self):
        svc = make_service(
            FakeResolver(["k1"]),
            FakeGraph(matches=[], labels={"k1": ("Trees", "AL")}),
        )
        resp = svc.discover("binary trees", "all")
        assert resp.status == "no_courses_found"
        assert len(resp.resolved_kus) == 1

    def test_ok_with_courses(self):
        graph = FakeGraph(
            matches=[
                make_match("CS-25100", "25100", ["k1", "k2"]),
                make_match("CS-18000", "18000", ["k1"]),
            ],
            labels={"k1": ("Trees", "AL"), "k2": ("Sorting", "AL")},
        )
        svc = make_service(FakeResolver(["k1", "k2"]), graph)
        resp = svc.discover("data structures", "all")
        assert resp.status == "ok"
        assert len(resp.courses) == 2
        # Ranked by relevance; both 0.8 → tiebreak by coverage breadth
        assert resp.courses[0].course_number == "25100"
        assert resp.courses[0].evidence_basis == "inferred"
        assert "of 2 concepts" in resp.courses[0].coverage_breadth

    def test_combinations_present(self):
        graph = FakeGraph(
            matches=[
                make_match("CS-1", "10000", ["k1", "k2"]),
                make_match("CS-2", "20000", ["k3", "k4"]),
            ],
            labels={f"k{i}": (f"KU{i}", "AL") for i in range(1, 5)},
        )
        svc = make_service(FakeResolver(["k1", "k2", "k3", "k4"]), graph)
        resp = svc.discover("broad topic", "all")
        assert len(resp.combinations) >= 1
        assert resp.combinations[0].combined_coverage_breadth == "4 of 4 concepts"

    def test_thin_coverage_disclosed(self):
        graph = FakeGraph(
            matches=[make_match("CS-1", "10000", ["k1"])],
            thin=["k2"],
            labels={"k1": ("Trees", "AL"), "k2": ("Rare Topic", "AL")},
        )
        svc = make_service(FakeResolver(["k1", "k2"]), graph)
        resp = svc.discover("mixed", "all")
        assert any(t.ku_id == "k2" for t in resp.thin_coverage)

    def test_level_filter(self):
        graph = FakeGraph(
            matches=[
                make_match("CS-1", "10000", ["k1"], level="undergraduate"),
                make_match("CS-5", "50000", ["k1"], level="graduate"),
            ],
            labels={"k1": ("Trees", "AL")},
        )
        svc = make_service(FakeResolver(["k1"]), graph)
        resp = svc.discover("x", "graduate")
        assert all(c.level == "graduate" for c in resp.courses)


class TestDiscoverEndpoint:
    def _client(self, resolver, graph) -> TestClient:
        app = create_app(APIConfig())
        app.dependency_overrides[get_discover_service] = lambda: make_service(resolver, graph)
        return TestClient(app)

    def test_empty_query_returns_400(self):
        client = self._client(FakeResolver([]), FakeGraph())
        resp = client.post("/api/v1/discover", json={"query": "", "level": "all"})
        assert resp.status_code == 422 or resp.status_code == 400

    def test_no_courses_returns_200(self):
        client = self._client(
            FakeResolver(["k1"]), FakeGraph(matches=[], labels={"k1": ("T", "AL")})
        )
        resp = client.post("/api/v1/discover", json={"query": "trees", "level": "all"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "no_courses_found"

    def test_ok_response_shape(self):
        graph = FakeGraph(
            matches=[make_match("CS-1", "10000", ["k1"])],
            labels={"k1": ("Trees", "AL")},
        )
        client = self._client(FakeResolver(["k1"]), graph)
        resp = client.post("/api/v1/discover", json={"query": "trees", "level": "all"})
        assert resp.status_code == 200
        body = resp.json()
        assert "courses" in body
        assert "combinations" in body
        assert body["status"] == "ok"

    def test_health(self):
        client = self._client(FakeResolver([]), FakeGraph())
        assert client.get("/health").json()["status"] == "ok"
