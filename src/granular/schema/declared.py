"""Declared facts — records that trace directly to an institution's published data."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Union

from granular.schema.errors import SchemaValidationError
from granular.schema.provenance import ProvenanceRecord


# ---------------------------------------------------------------------------
# Base type
# ---------------------------------------------------------------------------

@dataclass
class DeclaredFact:
    """Base type for all declared (institution-published) facts.

    Cannot be mixed with InferredFact in any field — enforced by the type
    system and by the absence of any union field accepting both.
    """

    provenance: ProvenanceRecord


# ---------------------------------------------------------------------------
# Prerequisite predicate tree
# ---------------------------------------------------------------------------

@dataclass
class SingleCourse:
    course_id: str
    min_grade: Optional[str] = None


@dataclass
class AndList:
    children: list["PredicateNode"]


@dataclass
class OrList:
    children: list["PredicateNode"]


PredicateNode = Union[SingleCourse, AndList, OrList]


@dataclass
class PrerequisiteRule:
    """Structured or verbatim representation of a prerequisite statement.

    Invariant: if machine_checkable=True, structured must be non-None.
               if machine_checkable=False, structured must be None and
               verbatim_text must be non-empty.
    """

    rule_id: str
    verbatim_text: str
    machine_checkable: bool
    structured: Optional[PredicateNode] = None

    def __post_init__(self) -> None:
        if self.machine_checkable and self.structured is None:
            raise SchemaValidationError(
                "PrerequisiteRule",
                "structured",
                None,
                "must be non-None when machine_checkable=True",
            )
        if not self.machine_checkable:
            if self.structured is not None:
                raise SchemaValidationError(
                    "PrerequisiteRule",
                    "structured",
                    self.structured,
                    "must be None when machine_checkable=False",
                )
            if not self.verbatim_text or not self.verbatim_text.strip():
                raise SchemaValidationError(
                    "PrerequisiteRule",
                    "verbatim_text",
                    self.verbatim_text,
                    "must be non-empty when machine_checkable=False",
                )


# ---------------------------------------------------------------------------
# DeclaredEdge
# ---------------------------------------------------------------------------

class DeclaredEdgeType(str, Enum):
    PREREQUISITE = "prerequisite"
    PROGRAMME_MEMBERSHIP = "programme_membership"
    CROSS_LISTING = "cross_listing"
    COREQUISITE = "corequisite"


@dataclass
class DeclaredEdge(DeclaredFact):
    """A typed relationship sourced from published institutional data.

    No confidence score. No model_id. These fields do not exist on this type.
    """

    edge_id: str = ""
    from_id: str = ""
    to_id: str = ""
    relationship_type: DeclaredEdgeType = DeclaredEdgeType.PREREQUISITE

    def __post_init__(self) -> None:
        for fname, val in [
            ("edge_id", self.edge_id),
            ("from_id", self.from_id),
            ("to_id", self.to_id),
        ]:
            if not val or not val.strip():
                raise SchemaValidationError(
                    "DeclaredEdge", fname, val, "must be a non-empty string"
                )
