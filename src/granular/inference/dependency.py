"""DependencyInferrer — produces concept_dependency edges from structural signals."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from granular.inference.config import InferenceConfig
from granular.inference.cycle import RejectedEdge, resolve_cycles
from granular.inference.ordering import OrderingValidator, ValidationResult
from granular.inference.scorer import ConceptNode, DependencyScorer
from granular.inference.snapshot import ConceptGraphSnapshot
from granular.schema import (
    InferredEdge,
    InferredEdgeType,
    ProvenanceRecord,
)

logger = logging.getLogger(__name__)


class DependencyInferrer:
    """Infers concept_dependency edges. No embedding-only edges are produced."""

    def __init__(
        self,
        config: InferenceConfig,
        scorer: DependencyScorer,
        validator: OrderingValidator,
    ) -> None:
        self._config = config
        self._scorer = scorer
        self._validator = validator

    def infer(
        self,
        concepts: list[ConceptNode],
        snapshot: ConceptGraphSnapshot,
        run_id: str,
    ) -> tuple[list[InferredEdge], list[RejectedEdge]]:
        """Produce concept_dependency edges from the concept set.

        Returns (surviving_edges, rejected_edges).
        """
        candidates: list[tuple[InferredEdge, float]] = []
        ordering_rejections: list[RejectedEdge] = []

        provenance = ProvenanceRecord(
            source_url="https://granular.local/inferred/concept-graph-inference",
            retrieved_at=datetime.now(tz=timezone.utc),
            adapter_name=self._config.adapter_name,
            adapter_version=self._config.adapter_version,
            source_revision=None,
        )

        # Index concepts by course level for the hard "never infer upward" filter
        def level(cn: ConceptNode) -> float:
            try:
                return int(cn.course_number[:1])
            except (ValueError, IndexError):
                return 3

        for a in concepts:
            for b in concepts:
                if a.concept_id == b.concept_id:
                    continue
                if a.source_course_id == b.source_course_id:
                    continue
                # Hard filter: never infer that a lower-level concept depends on
                # a strictly higher-level one.
                if level(b) > level(a):
                    continue

                score = self._scorer.score(a, b)
                if score < self._config.min_dependency_score:
                    continue

                # Ordering validation
                if self._validator.check(a, b) == ValidationResult.CONTRADICTION:
                    ordering_rejections.append(
                        RejectedEdge(
                            from_id=a.concept_id,
                            to_id=b.concept_id,
                            score=score,
                            reason="prerequisite_ordering_contradiction",
                        )
                    )
                    continue

                edge = InferredEdge(
                    provenance=provenance,
                    model_id=self._config.model_id,
                    confidence=min(1.0, score),
                    edge_id=f"dep-{a.concept_id}-{b.concept_id}-{uuid.uuid4().hex[:6]}",
                    from_id=a.concept_id,
                    to_id=b.concept_id,
                    relationship_type=InferredEdgeType.CONCEPT_DEPENDENCY,
                )
                candidates.append((edge, score))

        # Cycle resolution
        surviving, cycle_rejections = resolve_cycles(snapshot, candidates)
        all_rejections = ordering_rejections + cycle_rejections
        logger.info(
            "Dependency inference: %d edges, %d ordering rejections, %d cycle removals",
            len(surviving),
            len(ordering_rejections),
            len(cycle_rejections),
        )
        return surviving, all_rejections
