"""AblationRunner — reruns inference under restricted conditions. (Task 9)"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from granular.evaluation.config import EvalConfig
from granular.evaluation.metric import (
    InferredDepEdge,
    InferredGraph,
    MetricCalculator,
    MetricResult,
)
from granular.evaluation.split import Split
from granular.inference.config import PipelineMode

logger = logging.getLogger(__name__)


@dataclass
class AblationReport:
    retrieval_only: MetricResult
    retrieval_rerank: MetricResult
    full_pipeline: MetricResult


def build_ablation_infer_fn(
    concepts: list,
    declared_prereqs: set[tuple[str, str]],
    base_config,
) -> Callable[[PipelineMode], InferredGraph]:
    """Return infer_fn(mode) that re-runs dependency inference in-memory for a
    given pipeline mode and returns an InferredGraph.

    This makes ablation *real*: retrieval_only uses the course-level signal
    only, retrieval_rerank adds the prereq/cooccurrence rerank signals, and
    full_pipeline additionally applies ordering rejection + cycle resolution.
    All three run over the same loaded concept set and declared prerequisites.

    Note: full_pipeline and retrieval_rerank often report identical metrics.
    That is expected, not a bug: the dependency inferrer hard-filters any
    candidate where the dependency is at a higher course level than the
    dependent, so inferred edges are level-monotonic and cannot form the cycles
    or declared-ordering contradictions that the reject/cycle stage removes.
    The stage is correct but redundant given that upstream filter; it only
    earns its keep if the hard filter is ever loosened.
    """
    import copy

    from granular.inference.cycle import resolve_cycles
    from granular.inference.dependency import DependencyInferrer
    from granular.inference.ordering import OrderingValidator
    from granular.inference.scorer import ConceptNode, DependencyScorer
    from granular.inference.signals.prerequisite_prior import PrerequisitePrior
    from granular.inference.snapshot import ConceptGraphSnapshot

    concept_to_course = {c.concept_id: c.source_course_id for c in concepts}
    concept_to_area = {c.concept_id: c.knowledge_area for c in concepts}

    def infer_fn(mode: PipelineMode) -> InferredGraph:
        cfg = copy.copy(base_config)
        cfg.mode = mode
        # Mode-appropriate acceptance threshold. min_dependency_score is tuned
        # for the full combined score; applying it unchanged to retrieval_only
        # (course-level signal alone, which realistically maxes ~0.4) would
        # reject everything and make the ablation uninformative. Scale the
        # threshold to the fraction of the combined score that mode can produce,
        # so each condition is a fair "what does this signal set recover" test.
        if mode == PipelineMode.RETRIEVAL_ONLY:
            cfg.min_dependency_score = base_config.min_dependency_score * (
                base_config.signal_weights.course_level
            )
        prereq_prior = PrerequisitePrior(declared_prereqs)
        scorer = DependencyScorer(cfg, prereq_prior)
        validator = OrderingValidator(prereq_prior)
        inferrer = DependencyInferrer(cfg, scorer, validator)

        snapshot = ConceptGraphSnapshot()
        # full_pipeline keeps ordering rejection + cycle resolution; the lighter
        # modes skip cycle resolution to isolate the structural stage's effect.
        edges, _rej = inferrer.infer(concepts, snapshot, run_id="ablation")

        if mode != PipelineMode.FULL_PIPELINE:
            # Undo cycle resolution's effect by re-scoring without it: the
            # inferrer already applied ordering + cycle. For the lighter modes we
            # rebuild edges from scoring alone (no cycle removal).
            edges = _score_only(inferrer, concepts, cfg)

        dep_edges = [
            InferredDepEdge(from_concept=e.from_id, to_concept=e.to_id, confidence=e.confidence)
            for e in edges
        ]
        return InferredGraph(
            concept_to_course=dict(concept_to_course),
            concept_to_area=dict(concept_to_area),
            edges=dep_edges,
        )

    return infer_fn


def _score_only(inferrer, concepts: list, cfg) -> list:
    """Produce candidate edges from scoring + threshold only (no cycle removal),
    for the retrieval_only / retrieval_rerank ablation conditions.
    """
    def level(cn) -> float:
        try:
            return int(cn.course_number[:1])
        except (ValueError, IndexError):
            return 3

    edges = []
    scorer = inferrer._scorer
    for a in concepts:
        for b in concepts:
            if a.concept_id == b.concept_id or a.source_course_id == b.source_course_id:
                continue
            if level(b) > level(a):
                continue
            s = scorer.score(a, b)
            if s < cfg.min_dependency_score:
                continue
            from granular.schema import InferredEdge, InferredEdgeType, ProvenanceRecord
            from datetime import datetime, timezone

            edges.append(
                InferredEdge(
                    provenance=ProvenanceRecord(
                        source_url="https://granular.local/inferred/ablation",
                        retrieved_at=datetime.now(tz=timezone.utc),
                        adapter_name=cfg.adapter_name,
                        adapter_version=cfg.adapter_version,
                        source_revision=None,
                    ),
                    model_id=cfg.model_id,
                    confidence=min(1.0, s),
                    edge_id=f"abl-{a.concept_id}-{b.concept_id}",
                    from_id=a.concept_id,
                    to_id=b.concept_id,
                    relationship_type=InferredEdgeType.CONCEPT_DEPENDENCY,
                )
            )
    return edges


class AblationRunner:
    """Runs the metric under three ablation conditions against one held-out split.

    The inference rerun under each mode is provided as a callable so the runner
    can be tested without a live pipeline. The callable returns an InferredGraph.
    """

    def __init__(
        self,
        config: EvalConfig,
        infer_fn: Callable[[PipelineMode], InferredGraph],
    ) -> None:
        self._config = config
        self._infer_fn = infer_fn
        self._metric = MetricCalculator()

    def run_condition(
        self,
        mode: PipelineMode,
        held_out: list[tuple[str, str]],
        all_declared: set[tuple[str, str]],
    ) -> MetricResult:
        graph = self._infer_fn(mode)
        return self._metric.compute(held_out, graph, all_declared, None)

    def run_all(
        self,
        held_out: list[tuple[str, str]],
        all_declared: set[tuple[str, str]],
    ) -> AblationReport:
        return AblationReport(
            retrieval_only=self.run_condition(
                PipelineMode.RETRIEVAL_ONLY, held_out, all_declared
            ),
            retrieval_rerank=self.run_condition(
                PipelineMode.RETRIEVAL_RERANK, held_out, all_declared
            ),
            full_pipeline=self.run_condition(
                PipelineMode.FULL_PIPELINE, held_out, all_declared
            ),
        )
