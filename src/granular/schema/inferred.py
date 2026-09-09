"""Inferred facts — records produced by the pipeline, never by the institution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from granular.schema.errors import SchemaValidationError
from granular.schema.provenance import ProvenanceRecord


# ---------------------------------------------------------------------------
# Base type
# ---------------------------------------------------------------------------

@dataclass
class InferredFact:
    """Base type for all inferred (pipeline-produced) facts.

    Every inferred fact carries a model identifier and a confidence score.
    Cannot be mixed with DeclaredFact in any field.
    """

    provenance: ProvenanceRecord
    model_id: str    # non-empty; identifies the model or pipeline version
    confidence: float  # [0.0, 1.0]

    def __post_init__(self) -> None:
        if not self.model_id or not self.model_id.strip():
            raise SchemaValidationError(
                "InferredFact", "model_id", self.model_id, "must be non-empty"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise SchemaValidationError(
                "InferredFact",
                "confidence",
                self.confidence,
                "must be in [0.0, 1.0]",
            )


# ---------------------------------------------------------------------------
# InferredEdge
# ---------------------------------------------------------------------------

class InferredEdgeType(str, Enum):
    CONCEPT_DEPENDENCY = "concept_dependency"
    CONCEPT_SIMILARITY = "concept_similarity"
    CONCEPT_MEMBERSHIP = "concept_membership"


@dataclass
class InferredEdge(InferredFact):
    """A typed relationship produced by the inference pipeline.

    Inherits model_id and confidence from InferredFact.
    """

    edge_id: str = ""
    from_id: str = ""
    to_id: str = ""
    relationship_type: InferredEdgeType = InferredEdgeType.CONCEPT_DEPENDENCY

    def __post_init__(self) -> None:
        super().__post_init__()
        for fname, val in [
            ("edge_id", self.edge_id),
            ("from_id", self.from_id),
            ("to_id", self.to_id),
        ]:
            if not val or not val.strip():
                raise SchemaValidationError(
                    "InferredEdge", fname, val, "must be a non-empty string"
                )
