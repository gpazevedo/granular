"""Tests for the discover-relevance eval."""

from __future__ import annotations

from dataclasses import dataclass

from granular.evaluation.discover_eval import (
    QueryLabel,
    evaluate_discover_relevance,
)


@dataclass
class FakeResolution:
    ku_ids: list


class FakeResolver:
    """Maps a query string to a fixed resolved ku_id list."""

    def __init__(self, mapping: dict[str, list[str]]) -> None:
        self._mapping = mapping

    def resolve(self, query: str) -> FakeResolution:
        return FakeResolution(ku_ids=self._mapping.get(query, []))


KU_TO_AREA = {
    "KU-IS-1": "IS",
    "KU-IS-2": "IS",
    "KU-AR-1": "AR",
    "KU-IM-1": "IM",
}


class TestDiscoverEval:
    def test_perfect_resolution(self):
        labels = [QueryLabel(query="ml", expected_areas={"IS"})]
        resolver = FakeResolver({"ml": ["KU-IS-1", "KU-IS-2"]})
        report = evaluate_discover_relevance(labels, resolver, KU_TO_AREA)
        q = report.per_query[0]
        assert q.precision == 1.0
        assert q.recall == 1.0
        assert report.macro_f1 == 1.0

    def test_noisy_resolution_lowers_precision(self):
        # Resolves IS (correct) + AR (spurious) -> precision 0.5, recall 1.0
        labels = [QueryLabel(query="ml", expected_areas={"IS"})]
        resolver = FakeResolver({"ml": ["KU-IS-1", "KU-AR-1"]})
        report = evaluate_discover_relevance(labels, resolver, KU_TO_AREA)
        q = report.per_query[0]
        assert q.precision == 0.5
        assert q.recall == 1.0

    def test_missing_area_lowers_recall(self):
        # Expected IS+IM, resolves only IS -> recall 0.5
        labels = [QueryLabel(query="q", expected_areas={"IS", "IM"})]
        resolver = FakeResolver({"q": ["KU-IS-1"]})
        report = evaluate_discover_relevance(labels, resolver, KU_TO_AREA)
        q = report.per_query[0]
        assert q.recall == 0.5
        assert q.precision == 1.0

    def test_macro_average_over_queries(self):
        labels = [
            QueryLabel(query="a", expected_areas={"IS"}),
            QueryLabel(query="b", expected_areas={"AR"}),
        ]
        resolver = FakeResolver({"a": ["KU-IS-1"], "b": ["KU-IS-1"]})  # b wrong
        report = evaluate_discover_relevance(labels, resolver, KU_TO_AREA)
        # a: P=R=1 ; b: P=0 (resolved IS not AR), R=0
        assert report.macro_precision == 0.5
        assert report.macro_recall == 0.5

    def test_to_dict(self):
        labels = [QueryLabel(query="ml", expected_areas={"IS"})]
        resolver = FakeResolver({"ml": ["KU-IS-1"]})
        d = evaluate_discover_relevance(labels, resolver, KU_TO_AREA).to_dict()
        assert d["macro_f1"] == 1.0
        assert d["per_query"][0]["query"] == "ml"
