"""Programme, RequirementRule, and CourseSet schema records."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from granular.schema.authority import Authority
from granular.schema.declared import DeclaredFact
from granular.schema.errors import SchemaValidationError
from granular.schema.provenance import ProvenanceRecord


class ProgrammeLevel(str, Enum):
    UNDERGRADUATE = "undergraduate"
    GRADUATE = "graduate"


class RuleType(str, Enum):
    MINIMUM_CREDITS = "minimum_credits"
    COURSE_LIST = "course_list"
    COURSE_SET_REFERENCE = "course_set_reference"
    GPA_MINIMUM = "gpa_minimum"
    OTHER = "other"


@dataclass
class RequirementRule:
    """A single requirement rule within a programme.

    If machine_checkable=False, verbatim_text must be non-empty and
    structured_predicate must be None.
    """

    rule_id: str
    rule_type: RuleType
    verbatim_text: str
    machine_checkable: bool
    structured_predicate: Optional[dict] = None  # None when not machine_checkable

    def __post_init__(self) -> None:
        if not self.machine_checkable:
            if not self.verbatim_text or not self.verbatim_text.strip():
                raise SchemaValidationError(
                    "RequirementRule",
                    "verbatim_text",
                    self.verbatim_text,
                    "must be non-empty when machine_checkable=False",
                )
            if self.structured_predicate is not None:
                raise SchemaValidationError(
                    "RequirementRule",
                    "structured_predicate",
                    self.structured_predicate,
                    "must be None when machine_checkable=False",
                )


@dataclass
class CourseSet:
    """A named group of courses that a requirement draws from.

    When open_enumeration=True, verbatim_description must be non-empty.
    """

    set_id: str
    name: str
    courses: list[str]  # course_ids
    open_enumeration: bool
    verbatim_description: Optional[str] = None

    def __post_init__(self) -> None:
        if self.open_enumeration and not self.verbatim_description:
            raise SchemaValidationError(
                "CourseSet",
                "verbatim_description",
                self.verbatim_description,
                "must be non-empty when open_enumeration=True",
            )


@dataclass
class Programme(DeclaredFact):
    """A named degree or certificate programme.

    Must have at least one RequirementRule (even if not_machine_checkable).
    """

    programme_id: str = ""
    authority: Authority = Authority.DERIVED
    name: str = ""
    level: ProgrammeLevel = ProgrammeLevel.UNDERGRADUATE
    department: str = ""
    catalogue_url: str = ""
    requirement_rules: list[RequirementRule] = field(default_factory=list)

    def __post_init__(self) -> None:
        for fname, val in [
            ("programme_id", self.programme_id),
            ("name", self.name),
            ("department", self.department),
            ("catalogue_url", self.catalogue_url),
        ]:
            if not val or not val.strip():
                raise SchemaValidationError(
                    "Programme", fname, val, "must be a non-empty string"
                )
        if not self.requirement_rules:
            raise SchemaValidationError(
                "Programme",
                "requirement_rules",
                [],
                "must contain at least one RequirementRule",
            )
