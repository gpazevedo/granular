"""Tests for HeldOutSplit and MetricCalculator (Tasks 3, 4)."""

from __future__ import annotations

from granular.evaluation.config import EvalConfig
from granular.evaluation.metric import (
    InferredDepEdge,
    InferredGraph,
    MetricCalculator,
)
from granular.evaluation.split import HeldOutSplit


class TestHeldOutSplit:
    def test_reproducible_with_fixed_seed(self):
        keys = [f"CS-{i}->CS-{i - 100}" for i in range(200, 260)]
        cfg = EvalConfig(random_seed=42)
        s1 = HeldOutSplit().create(keys, cfg)
        s2 = HeldOutSplit().create(keys, cfg)
        assert s1.test == s2.test
        assert s1.train == s2.train

    def test_fraction_respected(self):
        keys = [f"k{i}" for i in range(100)]
        cfg = EvalConfig(held_out_fraction=0.20)
        split = HeldOutSplit().create(keys, cfg)
        assert abs(len(split.test) - 20) <= 1

    def test_train_test_disjoint(self):
        keys = [f"k{i}" for i in range(50)]
        cfg = EvalConfig()
        split = HeldOutSplit().create(keys, cfg)
        assert set(split.train).isdisjoint(set(split.test))

    def test_round_trip(self, tmp_path):
        keys = [f"k{i}" for i in range(30)]
        cfg = EvalConfig()
        split = HeldOutSplit().create(keys, cfg)
        p = tmp_path / "split.json"
        import json
        p.write_text(json.dumps(split.to_dict()))
        loaded = HeldOutSplit().load(p)
        assert loaded.test == split.test
        assert loaded.seed == split.seed


def make_graph() -> InferredGraph:
    # Two courses: CS-25100 (concept c1) requires CS-18000 (concept c2)
    # Inferred edge: c1 depends on c2 (recovers the prereq)
    return InferredGraph(
        concept_to_course={"c1": "CS-25100", "c2": "CS-18000"},
        concept_to_area={"c1": "AL", "c2": "SDF"},
        edges=[InferredDepEdge(from_concept="c1", to_concept="c2", confidence=0.8)],
    )


class TestMetricCalculator:
    def test_perfect_recovery(self):
        graph = make_graph()
        declared = {("CS-25100", "CS-18000")}
        held_out = [("CS-25100", "CS-18000")]
        m = MetricCalculator().compute(held_out, graph, declared)
        assert m.tp == 1
        assert m.fn == 0
        assert m.recall == 1.0

    def test_zero_recovery(self):
        # Graph has no edge → held-out prereq not recovered
        graph = InferredGraph(
            concept_to_course={"c1": "CS-25100", "c2": "CS-18000"},
            concept_to_area={"c1": "AL", "c2": "SDF"},
            edges=[],
        )
        declared = {("CS-25100", "CS-18000")}
        held_out = [("CS-25100", "CS-18000")]
        m = MetricCalculator().compute(held_out, graph, declared)
        assert m.tp == 0
        assert m.fn == 1
        assert m.recall == 0.0

    def test_confidence_band_filter(self):
        graph = make_graph()  # edge confidence 0.8 = high band
        declared = {("CS-25100", "CS-18000")}
        held_out = [("CS-25100", "CS-18000")]
        # High band should recover
        m_high = MetricCalculator().compute(held_out, graph, declared, "high")
        assert m_high.tp == 1
        # Low band should not (edge is high-confidence)
        m_low = MetricCalculator().compute(held_out, graph, declared, "low")
        assert m_low.tp == 0

    def test_all_bands(self):
        graph = make_graph()
        declared = {("CS-25100", "CS-18000")}
        held_out = [("CS-25100", "CS-18000")]
        bands = MetricCalculator().compute_all_bands(held_out, graph, declared)
        assert set(bands.keys()) == {"all", "high", "medium", "low"}

    def test_by_knowledge_area(self):
        graph = make_graph()
        declared = {("CS-25100", "CS-18000")}
        held_out = [("CS-25100", "CS-18000")]
        rows = MetricCalculator().compute_by_knowledge_area(
            held_out, graph, declared, {"SDF": "Software Dev Fundamentals"}, 0.4
        )
        assert len(rows) >= 1
