"""SimilarityInferrer — produces concept_similarity edges for same-KU concepts."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from granular.inference.config import InferenceConfig
from granular.inference.scorer import ConceptNode
from granular.schema import InferredEdge, InferredEdgeType, ProvenanceRecord

logger = logging.getLogger(__name__)


class SimilarityInferrer:
    """Infers concept_similarity edges between concepts sharing a knowledge unit."""

    def __init__(self, config: InferenceConfig) -> None:
        self._config = config

    def infer(
        self,
        concepts_by_ku: dict[str, list[tuple[ConceptNode, float]]],
    ) -> tuple[list[InferredEdge], int]:
        """Produce similarity edges. Returns (edges, low_confidence_count).

        concepts_by_ku maps ku_id -> list of (ConceptNode, alignment_confidence).
        """
        edges: list[InferredEdge] = []
        low_confidence_count = 0

        provenance = ProvenanceRecord(
            source_url="https://granular.local/inferred/concept-graph-inference",
            retrieved_at=datetime.now(tz=timezone.utc),
            adapter_name=self._config.adapter_name,
            adapter_version=self._config.adapter_version,
            source_revision=None,
        )

        for ku_id, members in concepts_by_ku.items():
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    node_a, conf_a = members[i]
                    node_b, conf_b = members[j]
                    # Skip same-course pairs
                    if node_a.source_course_id == node_b.source_course_id:
                        continue

                    confidence = min(conf_a, conf_b)
                    is_low = conf_a < 0.5 and conf_b < 0.5
                    if is_low:
                        low_confidence_count += 1

                    edges.append(
                        InferredEdge(
                            provenance=provenance,
                            model_id=self._config.model_id,
                            confidence=max(0.01, confidence),
                            edge_id=f"sim-{node_a.concept_id}-{node_b.concept_id}-{uuid.uuid4().hex[:6]}",
                            from_id=node_a.concept_id,
                            to_id=node_b.concept_id,
                            relationship_type=InferredEdgeType.CONCEPT_SIMILARITY,
                        )
                    )

        logger.info(
            "Similarity inference: %d edges (%d low-confidence)",
            len(edges),
            low_confidence_count,
        )
        return edges, low_confidence_count
