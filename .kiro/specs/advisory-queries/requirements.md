# Requirements — advisory-queries

## Context

This spec covers the primary student-facing capability: interest-driven discovery. A student submits a plain-English description of what they want to learn; the system resolves it to CS2023 knowledge units, finds courses with matching concept coverage, and returns a prioritised list with metrics.

The secondary advisory queries (credit consequence, overlap, readiness, unlock, programme fit) are included here as lower-priority requirements to be implemented after interest-driven discovery is working.

**Evidence basis:** every answer declares whether it is `declared`, `inferred`, or `mixed`. Answers containing inference carry a confidence score and a caveat. No answer uses entitlement language.

**Session-scoped input:** any completed-course list supplied to a query is not persisted. The system has no user accounts and no persistent learner state.

**Interface:** a Python backend API consumed by the Next.js frontend.

---

## Requirements — Interest-Driven Discovery (Primary)

### REQ-AQ-01 — Plain-English interest resolution

**User story:** As a student, I want to describe what I want to learn in plain English, so that I can explore courses without knowing CS2023 vocabulary in advance.

**Acceptance criteria:**

- WHEN a student submits a plain-English interest query, THE SYSTEM SHALL resolve it to one or more CS2023 knowledge units before any course matching occurs.
- THE SYSTEM SHALL NOT match the query directly against course description text or course titles (free-text matching is prohibited; all matching goes via the controlled vocabulary).
- THE SYSTEM SHALL use embedding similarity to retrieve candidate knowledge units, then apply the same reranking logic as the concept-extraction pipeline (metadata reranking, no department hard filter).
- THE SYSTEM SHALL record which model resolved the query to knowledge units.
- IF the query resolves to zero knowledge units, THE SYSTEM SHALL return a `no_concepts_resolved` response with a suggestion to rephrase, rather than falling through to course matching.

---

### REQ-AQ-02 — Course matching and ranking

**User story:** As a student, I want the system to find and rank courses by how well they cover what I asked about, so that the most relevant course appears first.

**Acceptance criteria:**

- FOR EACH resolved knowledge unit, THE SYSTEM SHALL find all `Course` records that have at least one aligned `Concept` mapping to that unit.
- THE SYSTEM SHALL rank courses by a composite score combining:
  - **Relevance score** — the mean alignment confidence of matched concept-to-knowledge-unit pairs for the course
  - **Coverage breadth** — the count of resolved knowledge units covered by the course, expressed as "N of M concepts"
- THE SYSTEM SHALL return results sorted by relevance score descending, with coverage breadth as a tiebreaker.
- THE SYSTEM SHALL return both undergraduate and graduate courses unless the student specifies a level filter.
- THE SYSTEM SHALL include the course title, course number, level, credit hours, and a short description excerpt alongside each result.

---

### REQ-AQ-03 — Result metrics display

**User story:** As a student, I want to see relevance and coverage metrics for each result, so that I can judge how well a course fits my interest without reading the full description.

**Acceptance criteria:**

- FOR EACH course in the result list, THE SYSTEM SHALL return: `relevance_score` (float, 0.0–1.0), `coverage_breadth` (string, format "N of M concepts"), `evidence_basis` (fixed value `inferred`), `confidence` (float, the mean alignment confidence contributing to this result), and a `caveat` string.
- THE SYSTEM SHALL attach a caveat to every result indicating that coverage is inferred from course descriptions and may not reflect actual course content.
- THE SYSTEM SHALL label the evidence basis as `inferred` on every interest-driven result.
- THE SYSTEM SHALL NOT use entitlement language (e.g. "this course will teach you", "you will master", "covers everything you need") anywhere in any result field. This SHALL be enforced as a rendering check in the frontend, not only as a style guideline.

---

### REQ-AQ-04 — No results response

**User story:** As a student, I want an informative response when no courses match, so that I understand why rather than seeing an empty list.

**Acceptance criteria:**

- IF no courses match the resolved knowledge units, THE SYSTEM SHALL return a `no_courses_found` response that includes: the knowledge units the query resolved to, a statement that no courses with aligned concepts were found for those units, and a suggestion to try related terms.
- THE SYSTEM SHALL NOT return an empty list without explanation.

---

### REQ-AQ-05 — Thin-coverage disclosure

**User story:** As a student, I want to know when the knowledge map has sparse coverage of what I asked about, so that I can interpret a short result list correctly.

**Acceptance criteria:**

- WHEN one or more of the resolved knowledge units are flagged `thin_coverage` by the concept-extraction layer (per REQ-CE-09), THE SYSTEM SHALL include a disclosure in the response stating which topic areas have limited course coverage in the extracted graph.
- THE SYSTEM SHALL NOT omit weakly-covered results; it SHALL return them with the thin-coverage disclosure attached.
- The disclosure SHALL name the specific knowledge unit labels that are thin, not just state generically that coverage is limited.

---

### REQ-AQ-06 — Level filter

**User story:** As a student, I want to filter results by course level (undergraduate or graduate), so that I see courses appropriate to my enrolment status.

**Acceptance criteria:**

- THE SYSTEM SHALL accept an optional `level` parameter with values `undergraduate`, `graduate`, or `all` (default: `all`).
- WHEN `level` is specified, THE SYSTEM SHALL exclude courses of the other level from results.
- WHEN `level` is `all`, THE SYSTEM SHALL include both and label each result with its level.

---

### REQ-AQ-14 — Course combinations

**User story:** As a student, I want to see combinations of courses that together cover my learning interest, so that I can plan a sequence of study when no single course is sufficient.

**Acceptance criteria:**

- AFTER ranking individual courses per REQ-AQ-02, THE SYSTEM SHALL compute course combinations of 2 or 3 courses that together cover a greater share of the resolved knowledge units than any single course in the result list covers alone.
- THE SYSTEM SHALL only produce combinations that improve on the best single-course coverage breadth; a combination that adds no additional knowledge unit coverage SHALL NOT be returned.
- THE SYSTEM SHALL cap combination size at 3 courses.
- FOR EACH combination, THE SYSTEM SHALL report: the participating courses (title, course number, level), combined coverage breadth (deduplicated union of covered knowledge units, in "N of M concepts" format), a redundancy flag per course pair within the combination indicating which knowledge units are covered by more than one course in the set, and an ordered prerequisite sequence drawn from declared edges (e.g. "take CS 182 before CS 381") where declared prerequisites exist between courses in the combination.
- IF no declared prerequisite relationship exists between courses in a combination, THE SYSTEM SHALL state that no ordering constraint is published between them.
- THE SYSTEM SHALL present combinations in a separate "Course Combinations" section in the response, not mixed into the individual course ranking.
- THE SYSTEM SHALL label the evidence basis of each combination as `inferred` and attach a caveat.
- THE SYSTEM SHALL NOT use entitlement language in combination results. This SHALL be enforced as a rendering check in the frontend.
- THE SYSTEM SHALL return at most 5 combinations per query (configurable).

---

## Requirements — Secondary Advisory Queries

### REQ-AQ-07 — Credit consequence (declared)

**User story:** As a student or advisor, I want to know what a given course counts toward, so that I can plan around published requirements.

**Acceptance criteria:**

- WHEN a user queries what a course counts toward, THE SYSTEM SHALL return only programme membership relationships present in the declared layer.
- IF no declared membership relationship exists for the course, THE SYSTEM SHALL report that no credit relationship is published, rather than inferring one.
- THE SYSTEM SHALL label the evidence basis as `declared`.

---

### REQ-AQ-08 — Overlap (inferred)

**User story:** As a student, I want to know whether a target course covers concepts I've already met, and which it doesn't, so that I can judge relevance without assuming exemption.

**Acceptance criteria:**

- WHEN a user queries overlap for a target course against a supplied completed-course list, THE SYSTEM SHALL return both matched concepts (already covered) and gap concepts (not covered).
- THE SYSTEM SHALL attach a confidence score and caveat to the overlap answer, and SHALL label the evidence basis as `inferred`.
- THE SYSTEM SHALL NOT use entitlement language (e.g. "exempt", "you can skip") anywhere in an overlap answer. This SHALL be enforced as a rendering check.
- THE SYSTEM SHALL treat the completed-course list as session-scoped input and SHALL NOT persist it after the query completes.

---

### REQ-AQ-09 — Readiness (declared)

**User story:** As a student, I want to know whether I can take a course given what I've completed, so that I can plan enrolment.

**Acceptance criteria:**

- WHEN a user queries readiness for a course, THE SYSTEM SHALL return the set of unmet prerequisites drawn from the declared layer.
- WHEN an unmet prerequisite is returned, THE SYSTEM SHALL include the catalogue's verbatim wording alongside the structured result.
- THE SYSTEM SHALL label the evidence basis as `declared`.

---

### REQ-AQ-10 — Unlock (declared)

**User story:** As a student, I want to know what a course opens up, so that I can see the forward consequence of taking it.

**Acceptance criteria:**

- WHEN a user queries unlock for a course, THE SYSTEM SHALL perform a forward prerequisite traversal over declared edges only and return the resulting course set.
- THE SYSTEM SHALL label the evidence basis as `declared`.

---

### REQ-AQ-11 — Programme fit (declared + structured)

**User story:** As a student or advisor, I want to know how far a course or plan would move me through a programme, so that I can gauge progress honestly.

**Acceptance criteria:**

- WHEN a programme-fit answer is computed, THE SYSTEM SHALL report the share of requirement rules that could not be structured (`not_machine_checkable`) alongside the progress figure.
- THE SYSTEM SHALL NOT render a progress indicator that omits the unstructured-rule share.
- THE SYSTEM SHALL label the evidence basis as `declared` for structured rules and note the incomplete coverage for unstructured rules.

---

## Requirements — Frontend (Next.js)

### REQ-AQ-12 — Interest discovery UI

**User story:** As a student, I want a simple interface to enter my learning interest and see ranked course results and course combinations, so that I can explore the curriculum without technical knowledge of the underlying system.

**Acceptance criteria:**

- THE FRONTEND SHALL provide a text input where a student can enter a plain-English learning interest description.
- THE FRONTEND SHALL display each individual result with: course number, title, level, credit hours, relevance score (as a visual indicator and numeric value), coverage breadth (in "N of M concepts" format), evidence basis label, and caveat text.
- THE FRONTEND SHALL display a separate "Course Combinations" section below the individual results, showing each combination with: participating courses, combined coverage breadth, redundancy flags (which concepts overlap between courses in the set), and prerequisite ordering notes.
- THE FRONTEND SHALL display thin-coverage disclosures when present.
- THE FRONTEND SHALL display the `no_concepts_resolved` and `no_courses_found` responses with their explanatory text, not as empty states.
- THE FRONTEND SHALL provide the level filter (undergraduate / graduate / all) as a UI control.
- THE FRONTEND SHALL NOT use entitlement language in any rendered text, including combination results. This is a rendering-level check, not only a backend concern.

---

### REQ-AQ-13 — API contract

**User story:** As a frontend developer, I want a documented, stable API contract for the interest-discovery endpoint, so that the frontend and backend can be developed independently.

**Acceptance criteria:**

- THE BACKEND SHALL expose a REST endpoint `POST /api/v1/discover` accepting: `{ "query": string, "level": "undergraduate" | "graduate" | "all" }`.
- THE BACKEND SHALL return a response conforming to a documented JSON schema covering all result fields in REQ-AQ-02, REQ-AQ-03, REQ-AQ-04, REQ-AQ-05, and REQ-AQ-14.
- The response SHALL contain two top-level sections: `courses` (individual ranked results) and `combinations` (course combination results per REQ-AQ-14).
- THE BACKEND SHALL return HTTP 400 for requests with a missing or empty `query` field.
- THE BACKEND SHALL return HTTP 200 with a `no_courses_found` response body (not HTTP 404) when no courses match.
- THE BACKEND SHALL include CORS headers permitting requests from the configured frontend origin.
