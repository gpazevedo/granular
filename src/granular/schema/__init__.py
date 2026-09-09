"""granular.schema — canonical data model for the Granular pipeline.

All downstream components import from this package. No network, no database,
no model dependencies.
"""

from granular.schema.authority import Authority
from granular.schema.concept import AlignmentStatus, Concept, KnowledgeTier, KnowledgeUnit
from granular.schema.course import Course, CreditRange
from granular.schema.declared import (
    AndList,
    DeclaredEdge,
    DeclaredEdgeType,
    DeclaredFact,
    OrList,
    PredicateNode,
    PrerequisiteRule,
    SingleCourse,
)
from granular.schema.errors import SchemaValidationError
from granular.schema.inferred import InferredEdge, InferredEdgeType, InferredFact
from granular.schema.programme import (
    CourseSet,
    Programme,
    ProgrammeLevel,
    RequirementRule,
    RuleType,
)
from granular.schema.provenance import ProvenanceRecord
from granular.schema.serialisation import (
    FailureDetail,
    ValidationReport,
    to_dict,
    to_json,
    validate_all,
)

__all__ = [
    # Authority
    "Authority",
    # Provenance
    "ProvenanceRecord",
    # Declared
    "DeclaredFact",
    "DeclaredEdge",
    "DeclaredEdgeType",
    "PrerequisiteRule",
    "PredicateNode",
    "SingleCourse",
    "AndList",
    "OrList",
    # Inferred
    "InferredFact",
    "InferredEdge",
    "InferredEdgeType",
    # Programme
    "Programme",
    "ProgrammeLevel",
    "RequirementRule",
    "RuleType",
    "CourseSet",
    # Course
    "Course",
    "CreditRange",
    # Concept
    "Concept",
    "KnowledgeUnit",
    "AlignmentStatus",
    "KnowledgeTier",
    # Errors
    "SchemaValidationError",
    # Serialisation
    "to_json",
    "to_dict",
    "validate_all",
    "ValidationReport",
    "FailureDetail",
]
