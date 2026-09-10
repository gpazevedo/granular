"""The dependency scorer must vary by pipeline mode (for real ablation)."""

from __future__ import annotations

from granular.inference.config import InferenceConfig, PipelineMode
from granular.inference.scorer import ConceptNode, DependencyScorer
from granular.inference.signals.prerequisite_prior import PrerequisitePrior


def _node(cid, course, cnum, area):
    return ConceptNode(
        concept_id=cid, label=cid, source_course_id=course, course_number=cnum, knowledge_area=area
    )


def _scorer(mode, declared=None):
    cfg = InferenceConfig(mode=mode)
    return DependencyScorer(cfg, PrerequisitePrior(declared or set()))


class TestModeAwareScoring:
    def test_retrieval_only_ignores_prereq_and_cooccurrence(self):
        # Same-area concepts with a declared prereq: rerank signals would boost
        # the score, but retrieval_only should use course-level only.
        dependent = _node("a", "CS-400", "400", "AL")
        dependency = _node("b", "CS-100", "100", "AL")
        declared = {("CS-400", "CS-100")}

        s_only = _scorer(PipelineMode.RETRIEVAL_ONLY, declared).score(dependent, dependency)
        s_full = _scorer(PipelineMode.FULL_PIPELINE, declared).score(dependent, dependency)

        # The two modes must produce different scores (signals genuinely differ).
        assert s_only != s_full

    def test_rerank_uses_all_signals(self):
        dependent = _node("a", "CS-400", "400", "AL")
        dependency = _node("b", "CS-100", "100", "AL")
        declared = {("CS-400", "CS-100")}
        s_rerank = _scorer(PipelineMode.RETRIEVAL_RERANK, declared).score(dependent, dependency)
        # With course-level + prereq + cooccurrence all positive, rerank score > 0.
        assert s_rerank > 0.0
