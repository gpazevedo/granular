# Requirements — canonical-schema

## Context

This spec defines the shared data model that all adapters produce and all downstream components consume. It is the first spec in the dependency chain. Nothing in `catalogue-ingestion`, `concept-extraction`, `concept-graph-inference`, `evaluation-harness`, or `advisory-queries` may introduce types that bypass or extend this schema without a change to this spec first.

The schema serves two layers:

- **Structural layer** — declared facts about programmes, courses, requirement rules, and the relationships the institution publishes
- **Concept layer** — inferred facts about concepts extracted from course prose, aligned to the CS2023 controlled vocabulary

All enforced invariants from steering §structure are implemented here as constructor-level validators.

---

## Requirements

### REQ-CS-01 — Provenance on every record

**User story:** As a developer consuming schema objects, I want every record to carry its origin metadata, so that I can audit any fact back to its source page and retrieval date.

**Acceptance criteria:**

- WHEN any schema object is constructed, THE SYSTEM SHALL require the following provenance fields: `source_url` (the URL the record was parsed from), `retrieved_at` (ISO-8601 UTC timestamp), `adapter_name` (string), `adapter_version` (semver string).
- IF the source document carries its own revision identifier (e.g. a catalogue year or edition string), THEN THE SYSTEM SHALL include it in a `source_revision` field; otherwise the field SHALL be present with a null value.
- THE SYSTEM SHALL reject construction of any schema object that is missing any required provenance field, raising a structured validation error that names the missing field.

---

### REQ-CS-02 — Declared and inferred facts as separate types

**User story:** As a developer, I want declared and inferred facts to be structurally separate types, so that it is impossible by construction to mix institutional ground truth with model-produced estimates.

**Acceptance criteria:**

- THE SYSTEM SHALL define `DeclaredFact` and `InferredFact` as distinct base types with no shared mutable fields.
- THE SYSTEM SHALL NOT provide any method, constructor, or coercion that accepts a `DeclaredFact` where an `InferredFact` is expected, or vice versa.
- WHEN a schema object contains a relationship, THE SYSTEM SHALL type that relationship as either `DeclaredEdge` or `InferredEdge`; a field SHALL NOT accept both.
- THE SYSTEM SHALL enforce the declared/inferred separation at the type level (not only at runtime), using Python type annotations and a runtime validator.

---

### REQ-CS-03 — Programme record

**User story:** As a downstream component, I want a well-typed Programme record, so that I can represent a named degree or certificate programme and its requirement structure without re-deriving its shape.

**Acceptance criteria:**

- THE SYSTEM SHALL define a `Programme` record with: `programme_id` (string, `authority` field), `name` (string), `level` (enum: `undergraduate` | `graduate`), `department` (string), `catalogue_url` (string), `requirement_rules` (list of `RequirementRule`), and provenance fields per REQ-CS-01.
- THE SYSTEM SHALL validate that `programme_id` carries an `authority` field with value `registrar` or `derived`.
- THE SYSTEM SHALL NOT allow a `Programme` to be constructed without at least one `RequirementRule`, even if that rule is `not_machine_checkable`.

---

### REQ-CS-04 — Course record

**User story:** As a downstream component, I want a well-typed Course record covering both undergraduate and graduate courses, so that concept extraction and advisory queries have a stable shape to work against.

**Acceptance criteria:**

- THE SYSTEM SHALL define a `Course` record with: `course_id` (string, with `authority` field), `subject_code` (string, e.g. `CS`), `course_number` (string), `title` (string), `description` (string), `credits` (numeric or credit-range), `level` (enum: `undergraduate` | `graduate`), `cross_listings` (list of course references, may be empty), `declared_prerequisites` (list of `PrerequisiteRule`), and provenance fields per REQ-CS-01.
- THE SYSTEM SHALL preserve the verbatim prerequisite text from the source alongside any structured representation.
- IF a prerequisite cannot be structured into a predicate, THE SYSTEM SHALL mark it `not_machine_checkable` and retain the verbatim text; it SHALL NOT be silently dropped.
- THE SYSTEM SHALL validate that `course_number` is non-empty and that `subject_code` is non-empty.

---

### REQ-CS-05 — RequirementRule record

**User story:** As a downstream component, I want requirement rules represented in a uniform structure, so that the programme-fit query can operate over them without parsing prose.

**Acceptance criteria:**

- THE SYSTEM SHALL define a `RequirementRule` record with: `rule_id` (string), `rule_type` (enum: `minimum_credits` | `course_list` | `course_set_reference` | `gpa_minimum` | `other`), `structured_predicate` (optional), `verbatim_text` (string, always present), `machine_checkable` (boolean).
- WHEN `machine_checkable` is `false`, THE SYSTEM SHALL require `verbatim_text` to be non-empty and `structured_predicate` to be null.
- THE SYSTEM SHALL define a `CourseSet` record with: `set_id`, `name`, `courses` (list of course references), `open_enumeration` (boolean). WHEN `open_enumeration` is `true`, THE SYSTEM SHALL record the verbatim set description.

---

### REQ-CS-06 — DeclaredEdge record

**User story:** As a downstream component, I want declared relationships between courses and programmes to be typed separately from inferred ones, so that the provenance invariant is enforced structurally.

**Acceptance criteria:**

- THE SYSTEM SHALL define a `DeclaredEdge` record with: `edge_id`, `from_id`, `to_id`, `relationship_type` (enum: `prerequisite` | `programme_membership` | `cross_listing` | `corequisite`), and provenance fields per REQ-CS-01.
- THE SYSTEM SHALL NOT allow a `DeclaredEdge` to carry a confidence score or a model identifier field.

---

### REQ-CS-07 — InferredEdge record

**User story:** As a downstream component, I want inferred relationships to carry confidence and model provenance, so that advisory queries can surface uncertainty correctly.

**Acceptance criteria:**

- THE SYSTEM SHALL define an `InferredEdge` record with: `edge_id`, `from_id`, `to_id`, `relationship_type` (enum: `concept_dependency` | `concept_similarity` | `concept_membership`), `confidence` (float 0.0–1.0), `model_id` (string, non-empty), and provenance fields per REQ-CS-01.
- THE SYSTEM SHALL reject construction of an `InferredEdge` with a null or empty `model_id`.
- THE SYSTEM SHALL reject construction of an `InferredEdge` with `confidence` outside [0.0, 1.0].

---

### REQ-CS-08 — Concept and KnowledgeUnit records

**User story:** As a downstream component, I want concept and knowledge-unit records that capture both the extracted concept and its CS2023 alignment, so that the advisory query can match student interests to course content via the controlled vocabulary.

**Acceptance criteria:**

- THE SYSTEM SHALL define a `Concept` record with: `concept_id` (string, `authority: derived`), `label` (string), `source_course_id` (string), `knowledge_unit_id` (optional string, null if not yet aligned), `model_id` (string, non-empty — the model that extracted the concept), and provenance fields per REQ-CS-01.
- THE SYSTEM SHALL define a `KnowledgeUnit` record with: `ku_id` (string), `label` (string), `knowledge_area` (string, CS2023 knowledge area code), `tier` (enum: `core` | `elective`), `source` (string, fixed value `CS2023`).
- THE SYSTEM SHALL NOT allow `Concept.model_id` to be null or empty.

---

### REQ-CS-09 — Validation error reporting

**User story:** As a developer, I want schema validation errors to be structured and informative, so that adapter bugs surface as clear failures rather than silent bad data.

**Acceptance criteria:**

- WHEN a schema object fails validation, THE SYSTEM SHALL raise a `SchemaValidationError` that includes: the record type, the field name that failed, the value that was rejected, and a human-readable reason.
- THE SYSTEM SHALL NOT swallow or log-and-continue on any validation error; all validation errors SHALL propagate to the caller.
- THE SYSTEM SHALL provide a `validate_all(records)` utility that validates a collection and returns a structured report of all failures rather than stopping at the first.

---

### REQ-CS-10 — Serialisation and deserialisation

**User story:** As a developer, I want schema objects to serialise to and deserialise from JSON without data loss, so that they can be stored, transported, and reloaded without re-parsing the source.

**Acceptance criteria:**

- THE SYSTEM SHALL provide `to_json()` and `from_json()` methods (or equivalent) for every schema record type.
- WHEN a record is serialised and then deserialised, THE SYSTEM SHALL produce an object that is equal to the original (all field values preserved, including provenance).
- THE SYSTEM SHALL reject deserialisation of a JSON object that is missing required fields, raising a `SchemaValidationError` per REQ-CS-09.
