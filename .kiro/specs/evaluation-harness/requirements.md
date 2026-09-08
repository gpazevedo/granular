# Requirements — evaluation-harness

## Context

This spec defines the measurement layer for the inference pipeline. Its job is to produce a honest, reproducible quality figure for the concept graph produced by `concept-graph-inference`, using only held-out declared data and blinded expert judgement — no opinion, no self-serving metrics.

The evaluation design follows §11 of the project definition directly. Three things are measured separately:

1. **Held-out declared prerequisites** — the pipeline's ability to recover withheld declared course prerequisite relationships from concept-level inference alone. This is the headline metric: mechanical, no hand-labelling required.
2. **Novel inferred relationships** — relationships never declared anywhere, judged by a domain expert against a pre-written rubric, blinded and mixed with plausible distractors.
3. **Ablation** — each pipeline component's individual contribution, measured by progressively disabling stages.

**Failure reporting is first-class.** Unstructured rules, rejected model outputs, and subdomains with poor accuracy are reported alongside successes. The harness does not produce a single optimistic number.

**Note on the §3.3 gate:** the original project definition deferred interest-driven discovery until this harness produced a quality figure. That gate has been lifted (see decisions.md). The harness is still required — it measures whether the concept graph is trustworthy enough to interpret advisory results correctly — but it no longer blocks the advisory queries spec.

---

## Requirements

### REQ-EH-01 — Held-out prerequisite split

**User story:** As a developer running evaluation, I want a reproducible train/test split of declared prerequisite edges, so that the headline metric is comparable across runs and cannot be gamed by changing the split.

**Acceptance criteria:**

- THE SYSTEM SHALL withhold a configurable fraction of declared `prerequisite` `DeclaredEdge` records (default: 20%) from the concept-graph-inference pipeline before inference runs.
- THE SYSTEM SHALL use a fixed random seed (configurable, default recorded in the evaluation config) to ensure the split is reproducible.
- Withheld edges SHALL be stored in a separate held-out set file that is written before inference begins and not modified during or after inference.
- THE SYSTEM SHALL NOT expose the withheld edges to any stage of the inference pipeline.
- THE SYSTEM SHALL record which catalogue year and ingestion run the split was derived from, so results are traceable to a specific data snapshot.

---

### REQ-EH-02 — Headline metric: prerequisite recovery

**User story:** As a developer and reader of results, I want a single mechanical metric measuring how well inferred concept dependencies recover withheld declared prerequisites, so that the quality of the inference layer can be stated as a number without editorial discretion.

**Acceptance criteria:**

- THE SYSTEM SHALL compute precision, recall, and F1 at the course-pair level: for each withheld declared prerequisite (course X requires course Y), check whether the inferred concept graph contains a directed concept dependency path from a concept in Y to a concept in X.
- THE SYSTEM SHALL report the headline metric as F1 at course-pair level, alongside precision and recall.
- THE SYSTEM SHALL compute and report the metric separately for: all edges, high-confidence edges only (≥ 0.7), medium-confidence edges (0.4–0.69), and low-confidence edges (< 0.4) per REQ-CGI-05.
- THE SYSTEM SHALL report results broken down by CS2023 knowledge area, not only as an aggregate.
- THE SYSTEM SHALL NOT report only aggregate results; subdomain breakdowns are required.

---

### REQ-EH-03 — Reproduction vs. contribution separation

**User story:** As a developer reporting results, I want inferred relationships separated into those that reproduce declared facts and those that are genuinely novel, so that the contribution claim is not inflated by reproduction.

**Acceptance criteria:**

- THE SYSTEM SHALL classify each inferred `concept_dependency` edge as either `reproduces_declared` (a declared prerequisite relationship exists at the course level for the same concept pair's courses) or `novel` (no declared relationship exists).
- THE SYSTEM SHALL report counts and confidence distributions separately for `reproduces_declared` and `novel` edges.
- THE SYSTEM SHALL NOT present `reproduces_declared` edges as evidence of contribution.

---

### REQ-EH-04 — Expert judgement protocol

**User story:** As a developer conducting evaluation, I want a structured protocol for blinded expert judgement of novel inferred relationships, so that the judgement is defensible and not self-serving.

**Acceptance criteria:**

- THE SYSTEM SHALL generate a judgement set by sampling novel inferred edges and mixing them with an equal number of plausible distractors (concept pairs with moderate embedding similarity but no inferred edge).
- THE SYSTEM SHALL NOT label which items in the judgement set are inferred vs. distractor; the set SHALL be presented blind.
- THE SYSTEM SHALL produce a rubric file before any judgement is recorded, containing: the judgement scale (at minimum: `correct`, `plausible_but_wrong`, `incorrect`), the definition of each scale point, and the domain area of each item.
- THE SYSTEM SHALL record per-item confidence from the inference pipeline alongside the expert judgement, so results can be stratified post-hoc.
- THE SYSTEM SHALL produce a final report comparing expert judgement to pipeline confidence, showing whether high-confidence edges earn higher expert approval rates.

---

### REQ-EH-05 — Ablation

**User story:** As a developer, I want to measure each pipeline component's individual contribution, so that the value of each stage is a number rather than an assumption.

**Acceptance criteria:**

- THE SYSTEM SHALL support running the headline metric (REQ-EH-02) under each of the following ablation conditions, independently:
  - **Retrieval only** — embedding similarity, no reranking, no structural rejection
  - **Retrieval + reranking** — stages 1–2 of the alignment pipeline, no structural rejection
  - **Full pipeline** — all stages including structural rejection
- THE SYSTEM SHALL produce a comparison table showing F1, precision, and recall for each ablation condition side by side.
- THE SYSTEM SHALL run ablations against the same held-out split as the full evaluation (REQ-EH-01).

---

### REQ-EH-06 — Failure reporting

**User story:** As a developer, I want failure modes reported prominently alongside successes, so that the evaluation is honest and gaps are visible.

**Acceptance criteria:**

- THE SYSTEM SHALL report the following failure counts in the evaluation output: prerequisite rules that could not be structured (`not_machine_checkable`), model outputs rejected by validation, inferred edges removed for cycle prevention, inferred edges rejected for prerequisite ordering contradiction.
- THE SYSTEM SHALL report subdomains (CS2023 knowledge areas) where F1 was below a configurable threshold (default: 0.4) as `poor_coverage_areas`.
- THE SYSTEM SHALL NOT produce a summary report that omits any of the above failure categories, even if the counts are zero.

---

### REQ-EH-07 — Department hard-filter regression test

**User story:** As a developer, I want a regression test that verifies the alignment pipeline never uses department as a hard filter, so that a future change cannot silently reintroduce this constraint.

**Acceptance criteria:**

- THE SYSTEM SHALL include a test case using at least one cross-listed CS course (shared with another department) and assert that the alignment results for that course are not affected by filtering on department.
- This test SHALL be run as part of the standard evaluation harness test suite.
- A failure of this test SHALL cause the harness to exit with a non-zero code.

---

### REQ-EH-08 — Scope-of-claim statement

**User story:** As a developer publishing results, I want the evaluation report to include a machine-generated scope statement, so that claims are not overstated.

**Acceptance criteria:**

- THE SYSTEM SHALL include in every evaluation report a fixed scope statement covering: the institution evaluated (Purdue University), the discipline (computer science), the catalogue year used, and the following caveat — that the genericity claim covers adapter genericity across the Modern Campus platform, not extraction genericity across disciplines.
- The scope statement SHALL be generated from the evaluation config (institution, catalogue year) and SHALL NOT be hand-written into the report.

---

### REQ-EH-09 — Reproducible evaluation artefacts

**User story:** As a developer, I want all evaluation inputs and outputs stored as versioned artefacts, so that the evaluation can be re-run and results compared across pipeline versions.

**Acceptance criteria:**

- THE SYSTEM SHALL write the following artefacts to a configurable output directory for each evaluation run: the held-out split file, the full inference output used as input, the ablation outputs, the judgement set (without labels), the completed judgement set (with labels, written after judgement), and the final report.
- Each artefact SHALL be named with a timestamp and a run identifier.
- THE SYSTEM SHALL produce a manifest file listing all artefacts and their checksums for each run.
