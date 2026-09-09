"""Concept and KnowledgeUnit schema records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from granular.schema.authority import Authority
from granular.schema.errors import SchemaValidationError
from granular.schema.inferred import InferredFact
from granular.schema.provenance import ProvenanceRecord


class AlignmentStatus(str, Enum):
    ALIGNED = "aligned"
    UNALIGNED = "unaligned"
    LOW_CONFIDENCE_UNALIGNED = "low_confidence_unaligned"


class KnowledgeTier(str, Enum):
    CORE = "core"
    ELECTIVE = "elective"


@dataclass
class KnowledgeUnit:
    """A knowledge unit from the CS2023 controlled vocabulary.

    Not an InferredFact — this is seed data bootstrapped from the CS2023 PDF,
    not produced by the pipeline's inference machinery.
    """

    ku_id: str
    label: str
    knowledge_area: str    # CS2023 knowledge area code, e.g. "AL"
    tier: KnowledgeTier
    source: str = "CS2023"  # fixed value

    def __post_init__(self) -> None:
        for fname, val in [
            ("ku_id", self.ku_id),
            ("label", self.label),
            ("knowledge_area", self.knowledge_area),
        ]:
            if not val or not val.strip():
                raise SchemaValidationError(
                    "KnowledgeUnit", fname, val, "must be a non-empty string"
                )
        if self.source != "CS2023":
            raise SchemaValidationError(
                "KnowledgeUnit", "source", self.source,
                "must be 'CS2023'",
            )


@dataclass
class Concept(InferredFact):
    """An atomic concept extracted from a course description.

    authority is always DERIVED — concepts are minted by this pipeline.
    model_id (inherited from InferredFact) records the model that extracted
    this concept; it must not be empty.
    knowledge_unit_id is None when the concept has not been aligned or
    alignment was rejected.
    """

    concept_id: str = ""
    authority: Authority = Authority.DERIVED
    label: str = ""
    source_course_id: str = ""
    knowledge_unit_id: Optional[str] = None
    alignment_status: AlignmentStatus = AlignmentStatus.UNALIGNED

    def __post_init__(self) -> None:
        super().__post_init__()   # validates model_id and confidence
        for fname, val in [
            ("concept_id", self.concept_id),
            ("label", self.label),
            ("source_course_id", self.source_course_id),
        ]:
            if not val or not val.strip():
                raise SchemaValidationError(
                    "Concept", fname, val, "must be a non-empty string"
                )
        if self.authority != Authority.DERIVED:
            raise SchemaValidationError(
                "Concept", "authority", self.authority,
                "Concept authority must always be DERIVED",
            )
