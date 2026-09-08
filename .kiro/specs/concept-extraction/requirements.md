# Requirements — concept-extraction

## Context

This spec covers two related tasks:

1. **CS2023 bootstrap** — a one-time extraction of knowledge areas, knowledge units, and topics from the CS2023 PDF, producing the controlled vocabulary seed file that all alignment depends on.
2. **Concept extraction and alignment** — for each ingested course, extract atomic concepts from the course description and align each concept to a CS2023 knowledge unit using the four-stage pipeline defined in §8.3 of the project definition.

The output feeds `concept-graph-inference` and `advisory-queries`. The alignment is probabilistic and is treated as such — all outputs carry confidence scores and model identifiers.

**Pipeline stages (from §8.3, in order):**

1. Retrieve — embed concept text, retrieve top-k candidate knowledge units
2. Rerank on metadata — co-occurrence with neighbouring concepts, normalised course level as depth proxy, department as soft prior only
3. Reject on structure — reject alignments that imply a dependency cycle or prerequisite ordering violation
4. Verify — constrained selection among retrieved candidates

---

## Requirements

### REQ-CE-01 — CS2023 vocabulary bootstrap

**User story:** As a developer, I want the CS2023 knowledge areas and knowledge units loaded into a machine-readable seed file, so that the alignment pipeline has a stable, inspectable controlled vocabulary to work against.

**Acceptance criteria:**

- THE SYSTEM SHALL provide a one-time bootstrap script that processes the CS2023 PDF and produces a structured vocabulary file containing: knowledge area code, knowledge area name, knowledge unit id, knowledge unit label, tier (`core` | `elective`), and estimated contact hours where stated.
- THE SYSTEM SHALL produce one `KnowledgeUnit` record per knowledge unit, conforming to the canonical schema.
- THE SYSTEM SHALL store the vocabulary as a versioned seed file (e.g. `data/cs2023_vocabulary.json`) that is committed to the repository.
- THE SYSTEM SHALL report the count of knowledge areas and knowledge units extracted at the end of the bootstrap run.
- IF the bootstrap script cannot parse a section of the PDF, THE SYSTEM SHALL log the page range and reason, and continue; it SHALL NOT silently drop sections.
- THE SYSTEM SHALL NOT re-run the bootstrap automatically during normal pipeline execution; it is a manual, one-time step.

---

### REQ-CE-02 — Concept extraction from course descriptions

**User story:** As a downstream component, I want atomic concepts extracted from each course description, so that the concept graph has a node set grounded in actual course content.

**Acceptance criteria:**

- FOR EACH `Course` record with a non-empty `description`, THE SYSTEM SHALL run concept extraction and produce one or more `Concept` records.
- THE SYSTEM SHALL use a language model for extraction and SHALL record the model identifier on every `Concept` record per REQ-CS-08.
- THE SYSTEM SHALL NOT concatenate provenance metadata (course number, department, level) into the text submitted to the model for embedding; metadata is used only at the reranking stage.
- IF a course description is empty or fewer than 20 characters, THE SYSTEM SHALL skip extraction, log the course ID and reason, and produce no `Concept` records for that course.
- THE SYSTEM SHALL record the source `course_id` on every extracted `Concept`.

---

### REQ-CE-03 — Alignment stage 1: Retrieve

**User story:** As a developer, I want the retrieval stage to use embedding similarity over the CS2023 vocabulary to produce candidate knowledge units, so that adjudication has a bounded candidate set grounded in semantic similarity.

**Acceptance criteria:**

- FOR EACH extracted `Concept`, THE SYSTEM SHALL embed the concept label text and retrieve the top-k candidate `KnowledgeUnit` records from the vector index (default k=10, configurable).
- THE SYSTEM SHALL store embeddings in pgvector.
- THE SYSTEM SHALL NOT use the retrieved similarity score as the final alignment decision; it provides candidates only.
- THE SYSTEM SHALL record which model produced the embeddings.

---

### REQ-CE-04 — Alignment stage 2: Rerank on metadata

**User story:** As a developer, I want candidate knowledge units reranked using co-occurrence and course-level signals, so that alignment uses information the embedding does not carry.

**Acceptance criteria:**

- THE SYSTEM SHALL rerank retrieved candidates using: co-occurrence with other concepts extracted from the same course (strongest signal), normalised course number as a depth proxy (higher course numbers bias toward advanced knowledge units), and department as a soft prior (not a hard filter).
- THE SYSTEM SHALL NOT use department as a hard filter at any reranking stage, given pervasive cross-listing.
- THE SYSTEM SHALL produce a reranked candidate list, retaining the original similarity scores alongside the reranking scores for inspection.

---

### REQ-CE-05 — Alignment stage 3: Reject on structure

**User story:** As a developer, I want structurally invalid alignments rejected before verification, so that the concept graph cannot contain dependency cycles or prerequisite ordering violations introduced by alignment errors.

**Acceptance criteria:**

- THE SYSTEM SHALL check each candidate alignment against the current concept graph for dependency cycles and prerequisite ordering violations.
- IF an alignment would introduce a cycle, THE SYSTEM SHALL reject that candidate and log the rejected alignment with reason `cycle_violation`.
- IF an alignment would violate prerequisite ordering (a concept in a lower-level course aligned to a knowledge unit that depends on a concept in a higher-level course), THE SYSTEM SHALL reject that candidate and log the reason `ordering_violation`.
- A concept with all candidates rejected SHALL be recorded as `unaligned` with the rejection reasons; it SHALL NOT be silently dropped.

---

### REQ-CE-06 — Alignment stage 4: Verify

**User story:** As a developer, I want final alignment selected by constrained verification among surviving candidates, so that the alignment decision is more reliable than open-ended extraction.

**Acceptance criteria:**

- THE SYSTEM SHALL select the final alignment for each concept by constrained selection among the candidates surviving stages 1–3.
- THE SYSTEM SHALL record the `confidence` of the selected alignment as a float [0.0, 1.0] on the `Concept` record.
- IF no candidate survives stages 1–3, THE SYSTEM SHALL mark the concept `unaligned` and set `knowledge_unit_id` to null.
- THE SYSTEM SHALL NOT produce an alignment with a confidence below a configurable minimum threshold (default 0.3); concepts below this threshold are marked `low_confidence_unaligned`.

---

### REQ-CE-07 — Department hard-filter regression test

**User story:** As a developer, I want an explicit regression test covering the no-department-hard-filter rule, so that a future change cannot silently reintroduce this constraint.

**Acceptance criteria:**

- THE SYSTEM SHALL include a test case using a cross-listed course (a CS course that is also listed under another department) and assert that the alignment pipeline does not exclude candidates solely because of department.
- This test SHALL be part of the `evaluation-harness` spec's test suite and SHALL be referenced from this spec.

---

### REQ-CE-08 — Extraction run summary

**User story:** As a developer, I want a structured summary after each extraction run, so that I can see coverage and alignment quality at a glance.

**Acceptance criteria:**

- WHEN an extraction run completes, THE SYSTEM SHALL produce a JSON summary containing: courses processed, concepts extracted (total), concepts aligned (with knowledge unit), concepts unaligned, concepts low-confidence-unaligned, concepts skipped (empty description), and alignment confidence distribution (mean, median, p10, p90).
- THE SYSTEM SHALL write the summary to a configurable output path.

---

### REQ-CE-09 — Thin-coverage disclosure

**User story:** As an advisory query component, I want to know when the extracted concept graph has thin coverage of a topic area, so that the interest-driven discovery query can disclose this to the student rather than silently returning a weak result.

**Acceptance criteria:**

- THE SYSTEM SHALL expose a query: given a list of `KnowledgeUnit` ids, return the count of `Course` records that have at least one aligned `Concept` for each unit.
- IF fewer than a configurable minimum number of courses (default 1) cover a knowledge unit, THE SYSTEM SHALL flag that unit as `thin_coverage`.
- The advisory query layer SHALL use this signal to disclose thin coverage to the student per REQ-AQ-05.
