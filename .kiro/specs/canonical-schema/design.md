# Design — canonical-schema

## Overview

The canonical schema is a Python package (`granular.schema`) containing typed dataclasses for every record type in the system. Validation is enforced at construction time via `__post_init__` validators. Serialisation uses Pydantic v2 for JSON round-trips. The schema has no runtime dependencies on Neo4j, pgvector, or any model — it is a pure data definition layer importable by any component.

---

## Package layout

```text
src/
  granular/
    schema/
      __init__.py          # public re-exports
      provenance.py        # ProvenanceRecord mixin
      authority.py         # Authority enum
      declared.py          # DeclaredFact base, DeclaredEdge, PrerequisiteRule
      inferred.py          # InferredFact base, InferredEdge
      programme.py         # Programme, RequirementRule, CourseSet
      course.py            # Course
      concept.py           # Concept, KnowledgeUnit
      errors.py            # SchemaValidationError
      serialisation.py     # to_json / from_json utilities, validate_all
```

---

## Component breakdown

### 1. ProvenanceRecord

A dataclass mixin carried by every schema object.

```python
@dataclass
class ProvenanceRecord:
    source_url: str
    retrieved_at: datetime          # UTC, timezone-aware
    adapter_name: str
    adapter_version: str            # semver string
    source_revision: Optional[str]  # catalogue year / edition, or None
```

Validator: `source_url` must be a non-empty string starting with `http`; `retrieved_at` must be timezone-aware; `adapter_name` and `adapter_version` must be non-empty.

---

### 2. Authority

```python
class Authority(str, Enum):
    REGISTRAR = "registrar"
    DERIVED   = "derived"
```

Used as a field on any minted identifier. Defaults to `derived`.

---

### 3. DeclaredFact and InferredFact base types

```python
@dataclass
class DeclaredFact:
    provenance: ProvenanceRecord

@dataclass
class InferredFact:
    provenance: ProvenanceRecord
    model_id: str       # non-empty; the model that produced this fact
    confidence: float   # [0.0, 1.0]
```

`InferredFact` validator: `model_id` non-empty; `confidence` in [0.0, 1.0].

These are abstract base types. No field in any schema object is typed as `Union[DeclaredFact, InferredFact]` — every field specifies one or the other concretely.

---

### 4. DeclaredEdge

```python
class DeclaredEdgeType(str, Enum):
    PREREQUISITE        = "prerequisite"
    PROGRAMME_MEMBERSHIP = "programme_membership"
    CROSS_LISTING       = "cross_listing"
    COREQUISITE         = "corequisite"

@dataclass
class DeclaredEdge(DeclaredFact):
    edge_id:           str
    from_id:           str
    to_id:             str
    relationship_type: DeclaredEdgeType
```

No confidence field. No model_id field. Construction fails if either is passed.

---

### 5. InferredEdge

```python
class InferredEdgeType(str, Enum):
    CONCEPT_DEPENDENCY  = "concept_dependency"
    CONCEPT_SIMILARITY  = "concept_similarity"
    CONCEPT_MEMBERSHIP  = "concept_membership"

@dataclass
class InferredEdge(InferredFact):
    edge_id:           str
    from_id:           str
    to_id:             str
    relationship_type: InferredEdgeType
```

Inherits `model_id` and `confidence` from `InferredFact`.

---

### 6. PrerequisiteRule

```python
@dataclass
class PrerequisiteRule:
    rule_id:            str
    verbatim_text:      str           # always present
    machine_checkable:  bool
    structured:         Optional[PredicateNode]  # None if not machine_checkable
```

`PredicateNode` is a recursive union type covering:

- `SingleCourse(course_id: str, min_grade: Optional[str])`
- `AndList(children: list[PredicateNode])`
- `OrList(children: list[PredicateNode])`

Validator: if `machine_checkable` is `True`, `structured` must be non-None; if `False`, `structured` must be None and `verbatim_text` must be non-empty.

---

### 7. RequirementRule and CourseSet

```python
class RuleType(str, Enum):
    MINIMUM_CREDITS      = "minimum_credits"
    COURSE_LIST          = "course_list"
    COURSE_SET_REFERENCE = "course_set_reference"
    GPA_MINIMUM          = "gpa_minimum"
    OTHER                = "other"

@dataclass
class RequirementRule:
    rule_id:              str
    rule_type:            RuleType
    verbatim_text:        str
    machine_checkable:    bool
    structured_predicate: Optional[dict]  # None if not machine_checkable

@dataclass
class CourseSet:
    set_id:           str
    name:             str
    courses:          list[str]    # course_ids
    open_enumeration: bool
    verbatim_description: Optional[str]  # required when open_enumeration=True
```

---

### 8. Programme

```python
class ProgrammeLevel(str, Enum):
    UNDERGRADUATE = "undergraduate"
    GRADUATE      = "graduate"

@dataclass
class Programme(DeclaredFact):
    programme_id:      str
    authority:         Authority
    name:              str
    level:             ProgrammeLevel
    department:        str
    catalogue_url:     str
    requirement_rules: list[RequirementRule]  # min length 1
```

Validator: `requirement_rules` must be non-empty.

---

### 9. Course

```python
@dataclass
class Course(DeclaredFact):
    course_id:              str
    authority:              Authority
    subject_code:           str       # e.g. "CS"
    course_number:          str       # e.g. "38100"
    title:                  str
    description:            str
    credits:                Union[float, CreditRange]
    level:                  ProgrammeLevel
    cross_listings:         list[str]           # course_ids, may be empty
    declared_prerequisites: list[PrerequisiteRule]

@dataclass
class CreditRange:
    min_credits: float
    max_credits: float
```

Validator: `subject_code` and `course_number` non-empty.

---

### 10. Concept and KnowledgeUnit

```python
@dataclass
class Concept(InferredFact):
    concept_id:       str
    authority:        Authority   # always DERIVED
    label:            str
    source_course_id: str
    knowledge_unit_id: Optional[str]   # None if unaligned
    alignment_status: AlignmentStatus

class AlignmentStatus(str, Enum):
    ALIGNED               = "aligned"
    UNALIGNED             = "unaligned"
    LOW_CONFIDENCE_UNALIGNED = "low_confidence_unaligned"

@dataclass
class KnowledgeUnit:
    ku_id:          str
    label:          str
    knowledge_area: str    # CS2023 knowledge area code
    tier:           KnowledgeTier
    source:         str    # fixed: "CS2023"

class KnowledgeTier(str, Enum):
    CORE     = "core"
    ELECTIVE = "elective"
```

---

### 11. SchemaValidationError

```python
class SchemaValidationError(Exception):
    record_type: str
    field_name:  str
    value:       Any
    reason:      str
```

Raised by every `__post_init__` validator. Never swallowed.

---

### 12. Serialisation

All schema types are also Pydantic v2 `BaseModel` subclasses (via a dual-inheritance pattern or by generating Pydantic models from the dataclasses). This gives:

- `model.model_dump_json()` → JSON string
- `RecordType.model_validate_json(json_str)` → validated instance

`validate_all(records: list) -> ValidationReport`:

- Runs validation on every record
- Returns `ValidationReport(passed: list, failed: list[FailureDetail])`
- Never raises; collects all failures

---

## Invariant enforcement summary

| Invariant (from steering §structure) | Enforcement point |
| --- | --- |
| Provenance on every record | `ProvenanceRecord.__post_init__` |
| Declared and inferred are separate types | Type system — no union field exists |
| Concepts carry model_id | `InferredFact.__post_init__` |
| Minted identifiers carry `authority: derived` | `Authority` enum + `Concept.__post_init__` asserts `authority == DERIVED` |
| Unstructured requirements retain verbatim text | `RequirementRule.__post_init__` + `PrerequisiteRule.__post_init__` |

---

## Dependencies

- Python ≥ 3.11
- `pydantic` v2
- No database, no model, no network dependency
