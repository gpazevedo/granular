"""Course schema record."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from granular.schema.authority import Authority
from granular.schema.declared import DeclaredFact, PrerequisiteRule
from granular.schema.errors import SchemaValidationError
from granular.schema.programme import ProgrammeLevel
from granular.schema.provenance import ProvenanceRecord


@dataclass
class CreditRange:
    """A variable credit range, e.g. 1–3 credits."""

    min_credits: float
    max_credits: float

    def __post_init__(self) -> None:
        if self.min_credits < 0 or self.max_credits < 0:
            raise SchemaValidationError(
                "CreditRange", "min_credits/max_credits", (self.min_credits, self.max_credits),
                "credit values must be non-negative",
            )
        if self.min_credits > self.max_credits:
            raise SchemaValidationError(
                "CreditRange", "min_credits", self.min_credits,
                f"min_credits ({self.min_credits}) must be <= max_credits ({self.max_credits})",
            )


@dataclass
class Course(DeclaredFact):
    """A single course in the catalogue."""

    course_id: str = ""
    authority: Authority = Authority.DERIVED
    subject_code: str = ""      # e.g. "CS"
    course_number: str = ""     # e.g. "38100"
    title: str = ""
    description: str = ""
    credits: Union[float, CreditRange] = 0.0
    level: ProgrammeLevel = ProgrammeLevel.UNDERGRADUATE
    cross_listings: list[str] = field(default_factory=list)           # course_ids
    declared_prerequisites: list[PrerequisiteRule] = field(default_factory=list)

    def __post_init__(self) -> None:
        for fname, val in [
            ("course_id", self.course_id),
            ("subject_code", self.subject_code),
            ("course_number", self.course_number),
            ("title", self.title),
        ]:
            if not val or not val.strip():
                raise SchemaValidationError(
                    "Course", fname, val, "must be a non-empty string"
                )
