"""Tests for DependencyScorer and DependencyInferrer (network-free)."""

from __future__ import annotations

from granular.inference.config import InferenceConfig
from granular.inference.dependency import DependencyInferrer
from granular.inference.ordering import OrderingValidator
from granular.inference.scorer import ConceptNode, DependencyScorer
from granular.inference.signals.prerequisite_prior import PrerequisitePrior
from granular.inference.snapshot import ConceptGraphSnapshot


def node(cid: str, course: str, area: str = "AL") -> ConceptNode:
    return ConceptNode(
        concept_id=cid,
        label=cid,
        source_course_id=course,
        course_number=course.split("-")[1],
        knowledge_area=area,
    )


class TestDependencyScorer:
    def test_prereq_boosts_score(self):
        prior = PrerequisitePrior({("CS-25100", "CS-18000")})
        cfg = InferenceConfig()
        scorer = DependencyScorer(cfg, prior)
        # 25100 depends on 18000, declared prereq present → high score
        score = scorer.score(node("a", "CS-25100"), node("b", "CS-18000"))
        assert score > cfg.min_dependency_score

    def test_no_signal_low_score(self):
        prior = PrerequisitePrior(set())
        cfg = InferenceConfig()
        scorer = DependencyScorer(cfg, prior)
        # Same level, no prereq, different area
        score = scorer.score(node("a", "CS-25100", "AL"), node("b", "CS-25200", "IS"))
        # Different area still gives cooccurrence 0.5 * 0.15 = 0.075, level 0, prereq 0
        assert score < cfg.min_dependency_score


class TestDependencyInferrer:
    def _make_inferrer(self, declared):
        cfg = InferenceConfig()
        prior = PrerequisitePrior(declared)
        scorer = DependencyScorer(cfg, prior)
        validator = OrderingValidator(prior)
        return DependencyInferrer(cfg, scorer, validator), cfg

    def test_infers_edge_with_declared_prereq(self):
        inferrer, cfg = self._make_inferrer({("CS-25100", "CS-18000")})
        concepts = [
            node("cA", "CS-25100", "AL"),
            node("cB", "CS-18000", "AL"),
        ]
        snap = ConceptGraphSnapshot()
        edges, rejections = inferrer.infer(concepts, snap, "run-1")
        # Should infer cA depends on cB (higher level + declared prereq)
        assert any(e.from_id == "cA" and e.to_id == "cB" for e in edges)

    def test_never_infers_upward(self):
        inferrer, cfg = self._make_inferrer(set())
        concepts = [
            node("cLow", "CS-18000", "AL"),
            node("cHigh", "CS-48000", "AL"),
        ]
        snap = ConceptGraphSnapshot()
        edges, _ = inferrer.infer(concepts, snap, "run-1")
        # Low-level concept must never depend on a higher-level one
        assert not any(e.from_id == "cLow" and e.to_id == "cHigh" for e in edges)

    def test_no_self_or_same_course_edges(self):
        inferrer, cfg = self._make_inferrer({("CS-25100", "CS-25100")})
        concepts = [
            node("c1", "CS-25100", "AL"),
            node("c2", "CS-25100", "AL"),
        ]
        snap = ConceptGraphSnapshot()
        edges, _ = inferrer.infer(concepts, snap, "run-1")
        # No edges between concepts in the same course
        assert len(edges) == 0
