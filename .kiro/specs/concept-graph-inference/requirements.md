# Requirements — concept-graph-inference

## Context

This spec covers the inference of concept-level dependency relationships that are not explicitly declared by Purdue or any source. Given the concept graph produced by `concept-extraction` (concepts aligned to CS2023 knowledge units, associated with courses), this pipeline infers which concepts depend on which other concepts — i.e. which concepts a student likely needs before a given concept makes sense.

This is the probabilistic core of the system. It is what allows the advisory queries to go beyond what the institution has published. All outputs are `InferredEdge` records, never `DeclaredEdge`, and all carry confidence scores and model identifiers.

**Two categories of inferred relationship:**
- **Concept dependency** — concept A depends on concept B (B is a prerequisite for A at the concept level, not the course level)
- **Concept similarity** — concept A and concept B are closely related without a clear dependency direction (e.g. two formulations of the same idea)

**Input:** aligned `Concept` records and `KnowledgeUnit` records from `concept-extraction`, plus `DeclaredEdge` records of type `prerequisite` from `catalogue-ingestion` (used as a training signal and as a validation constraint, never as output).

**Key constraint from §8.1:** cosine similarity alone cannot distinguish *same concept, different name* from *different concepts, same neighbourhood*. The inference pipeline must not rely on embedding similarity as the sole signal for any edge decision.

---

## Requirements

### REQ-CGI-01 — Dependency inference from course co-occurrence

**User story:** As a downstream advisory query, I want concept dependency edges inferred from the structure of the curriculum, so that the system can answer concept-level readiness and gap questions that go beyond declared course prerequisites.

**Acceptance criteria:**

- THE SYSTEM SHALL infer `concept_dependency` edges between concepts using curriculum structure signals: concepts appearing in lower-numbered courses before higher-numbered courses that share aligned knowledge units, and declared course-level prerequisite edges as a structural prior.
- THE SYSTEM SHALL produce one `InferredEdge` of type `concept_dependency` per inferred dependency pair, conforming to the canonical schema with a `confidence` score and `model_id`.
- THE SYSTEM SHALL NOT produce a `concept_dependency` edge based on embedding similarity alone; at least one curriculum-structure signal must contribute to every inferred edge.
- THE SYSTEM SHALL NOT merge inferred edges with declared prerequisite edges; they remain separate types in the graph.

---

### REQ-CGI-02 — Concept similarity inference

**User story:** As a downstream advisory query, I want concept similarity edges captured, so that the overlap query can detect when two differently-named concepts in different courses refer to the same underlying idea.

**Acceptance criteria:**

- THE SYSTEM SHALL infer `concept_similarity` edges between concept pairs that resolve to the same `KnowledgeUnit` but originate from different courses.
- FOR EACH such pair, THE SYSTEM SHALL assign a `confidence` based on the alignment confidence of both ends: `min(confidence_A, confidence_B)`.
- THE SYSTEM SHALL NOT infer a `concept_similarity` edge between concepts in the same course.
- THE SYSTEM SHALL flag pairs where both concepts map to the same knowledge unit but have low alignment confidence (both below 0.5) as `low_confidence_similarity`; these SHALL be included in the graph but marked separately.

---

### REQ-CGI-03 — Cycle prevention

**User story:** As a developer, I want the inference pipeline to guarantee the concept dependency graph is a DAG, so that traversal queries cannot loop.

**Acceptance criteria:**

- AFTER each batch of inferred `concept_dependency` edges is added, THE SYSTEM SHALL check for cycles in the dependency subgraph.
- IF a cycle is detected, THE SYSTEM SHALL remove the lowest-confidence edge in the cycle, log the removed edge with reason `cycle_prevention`, and re-check until no cycle remains.
- THE SYSTEM SHALL report the count of edges removed for cycle prevention in the inference run summary.
- THE SYSTEM SHALL NOT raise an unhandled exception on cycle detection; cycle resolution is a normal pipeline step.

---

### REQ-CGI-04 — Prerequisite ordering validation

**User story:** As a developer, I want inferred concept dependencies checked against declared course prerequisites, so that the concept graph does not contradict what the institution has published.

**Acceptance criteria:**

- FOR EACH inferred `concept_dependency` edge from concept A (in course X) to concept B (in course Y), THE SYSTEM SHALL check whether declared course prerequisites are consistent with the inferred direction (i.e. course X is not declared a prerequisite of course Y when the inferred edge says A depends on B and A is in Y).
- IF an inferred edge contradicts a declared prerequisite direction, THE SYSTEM SHALL reject the edge, log it with reason `prerequisite_ordering_contradiction`, and record it in the run summary.
- Rejected edges SHALL be stored separately as `rejected_inferred_edges` for inspection; they SHALL NOT be added to the live graph.

---

### REQ-CGI-05 — Confidence stratification

**User story:** As a developer and as the evaluation harness, I want inferred edges stratified by confidence band, so that results can be reported and filtered by quality tier.

**Acceptance criteria:**

- THE SYSTEM SHALL stratify all inferred edges into three confidence bands: high (≥ 0.7), medium (0.4–0.69), low (< 0.4). Band thresholds SHALL be configurable.
- THE SYSTEM SHALL expose a query returning edges filtered by confidence band.
- The evaluation harness SHALL be able to run against each band independently (per REQ-EH-05).

---

### REQ-CGI-06 — Knowledge area coverage report

**User story:** As a developer, I want to know which CS2023 knowledge areas are well-represented and which are sparse in the inferred graph, so that I can interpret advisory query results correctly.

**Acceptance criteria:**

- WHEN an inference run completes, THE SYSTEM SHALL produce a per-knowledge-area breakdown showing: count of concepts, count of inferred dependency edges, count of inferred similarity edges, and mean confidence per area.
- Knowledge areas with zero inferred edges SHALL be explicitly listed as `no_inferred_edges`, not omitted.

---

### REQ-CGI-07 — Inference run summary

**User story:** As a developer, I want a structured summary after each inference run, so that I can assess pipeline health without reading individual log lines.

**Acceptance criteria:**

- WHEN an inference run completes, THE SYSTEM SHALL produce a JSON summary containing: concepts processed, `concept_dependency` edges inferred, `concept_similarity` edges inferred, edges rejected (by reason), edges removed for cycle prevention, edges rejected for prerequisite ordering contradiction, confidence distribution (mean, median, p10, p90), and run duration.
- THE SYSTEM SHALL write the summary to a configurable output path.
- THE SYSTEM SHALL exit with a non-zero code if the ratio of rejected edges to total candidate edges exceeds a configurable threshold (default: 20%).

---

### REQ-CGI-08 — openCypher-only graph queries

**User story:** As a developer, I want all graph queries in the inference pipeline written in openCypher with no store-specific extensions, so that the graph store can be replaced without rewriting any query.

**Acceptance criteria:**

- THE SYSTEM SHALL NOT call any store-specific procedure or plugin in any graph query (no APOC, no GDS, no proprietary functions).
- THE SYSTEM SHALL route all graph reads and writes through the `GraphClient` interface defined in `canonical-schema` (REQ-CS-11), whose connection details are supplied by configuration.
- ALL queries written in this pipeline SHALL pass validation against the openCypher specification.
