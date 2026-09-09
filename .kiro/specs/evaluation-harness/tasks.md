# Tasks — evaluation-harness

## Prerequisites

These specs must be complete before any task in this spec can be implemented:
- `canonical-schema` — `InferredEdge`, `DeclaredEdge`, `SchemaValidationError`
- `concept-graph-inference` — `ConceptGraphSnapshot`, `PipelineMode` flag, `InferenceSummary`

---

## Task 1 — Package scaffold and EvalConfig

**Implements:** design §1 (EvalConfig), package layout

- [ ] Create `src/granular/evaluation/` package with `__init__.py`
- [ ] Implement `EvalConfig` dataclass in `config.py` with all fields from the design: `neo4j_uri`, `neo4j_user`, `neo4j_password`, `held_out_fraction` (default 0.20), `random_seed` (default 42), `min_f1_poor_threshold` (default 0.40), `confidence_high` (default 0.70), `confidence_medium_low` (default 0.40), `distractor_ratio` (default 1.0), `institution`, `discipline`, `catalogue_year`, `ingestion_run_id`, `output_dir`, `artefact_dir`
- [ ] Implement `EvalConfig.from_toml(path: Path) -> EvalConfig` loading from a TOML file
- [ ] Implement `EvalConfig.from_env() -> EvalConfig` reading `GRANULAR_*` environment variables as overrides
- [ ] Add `__post_init__` validator: `held_out_fraction` must be in (0, 1); `random_seed` must be a non-negative int; `confidence_high` > `confidence_medium_low`
- [ ] Create `data/evaluation/runs/.gitkeep` so the directory is tracked
- [ ] Write unit tests for `EvalConfig` validation (valid config, each invalid field, env override)

---

## Task 2 — ArtefactStore

**Implements:** REQ-EH-09, design §10

- [ ] Implement `ArtefactStore` in `artefacts.py`
- [ ] `init_run(run_id: str) -> Path` — creates `{artefact_dir}/{run_id}/` directory; raises if it already exists unless `--resume` is set
- [ ] `write(name: str, data: dict | str) -> Path` — writes `{name}.json` (dict) or `{name}.md` (str) to the run directory; records filename and `written_at` in an internal manifest list
- [ ] `finalise_manifest() -> Path` — computes sha256 checksum for every written file; writes `manifest.json` with `[{filename, sha256, written_at}]`
- [ ] Artefact filenames include the run_id prefix: `{run_id}_{name}.json`
- [ ] Write unit tests: write multiple artefacts, call `finalise_manifest`, assert manifest contains correct checksums; assert re-writing an existing artefact raises

---

## Task 3 — HeldOutSplit

**Implements:** REQ-EH-01, design §2

- [ ] Implement `Split` dataclass in `split.py`: `train: list[str]`, `test: list[str]`, `seed: int`, `fraction: float`, `ingestion_run_id: str`, `created_at: datetime`
- [ ] Implement `HeldOutSplit.create(declared_edges: list[DeclaredEdge], config: EvalConfig) -> Split`:
  - Filters to `DeclaredEdge` records with `relationship_type == PREREQUISITE`
  - Shuffles with `random.Random(config.random_seed)`
  - Takes last `floor(len * held_out_fraction)` as test set
  - Records `ingestion_run_id` and `created_at` from config
  - Writes `split.json` via `ArtefactStore.write()`
  - Returns `Split`
- [ ] Implement `HeldOutSplit.load(path: Path) -> Split` — deserialises from JSON; validates required fields present
- [ ] Add guard: `HeldOutSplit.create` raises `RuntimeError` if the split file already exists for this run_id (prevents accidental overwrite)
- [ ] Write unit tests: fixed seed produces identical split across two calls; fraction is respected within ±1 edge; split file is written with correct metadata

---

## Task 4 — MetricCalculator

**Implements:** REQ-EH-02, design §3

- [ ] Implement `MetricResult` dataclass: `precision`, `recall`, `f1`, `tp`, `fp`, `fn`, `confidence_filter: Optional[str]`
- [ ] Implement `KAMetricResult` dataclass: `knowledge_area`, `knowledge_area_label`, `precision`, `recall`, `f1`, `sample_size`, `poor_coverage: bool`
- [ ] Implement `MetricCalculator.compute(held_out, inferred_graph, confidence_filter=None) -> MetricResult`:
  - For each held-out `DeclaredEdge(PREREQUISITE)` (course X → course Y): BFS (max depth 5) over `DEPENDS_ON` edges in `inferred_graph` restricted to concepts from Y, checking for path reaching any concept from X → TP
  - Held-out pairs with no such path → FN
  - Inferred course-pair paths not in any declared prerequisite set (train + test) → FP
  - Compute precision = TP / (TP + FP), recall = TP / (TP + FN), F1 = harmonic mean
  - When `confidence_filter` is set (`"high"`, `"medium"`, `"low"`), restrict BFS to edges in the corresponding confidence band
- [ ] Implement `MetricCalculator.compute_by_knowledge_area(held_out, inferred_graph) -> list[KAMetricResult]`:
  - Group held-out edges by the knowledge area of the concepts in the prerequisite course
  - Compute `MetricResult` per group
  - Set `poor_coverage = f1 < config.min_f1_poor_threshold`
- [ ] Implement `MetricCalculator.compute_all_bands(held_out, inferred_graph) -> dict[str, MetricResult]` — runs `compute()` for `None`, `"high"`, `"medium"`, `"low"` and returns all four
- [ ] Write unit tests: perfect recall (all held-out paths present), zero recall (no paths), mixed; BFS depth limit enforced; confidence filter correctly restricts edges

---

## Task 5 — ReproductionClassifier

**Implements:** REQ-EH-03, design §5

- [ ] Implement `EdgeClass` enum: `REPRODUCES_DECLARED`, `NOVEL`
- [ ] Implement `ReproductionClassifier.classify(edge: InferredEdge, all_declared_prereqs: set[tuple[str, str]]) -> EdgeClass`:
  - Resolves `edge.from_id` and `edge.to_id` to their source course IDs via the concept graph
  - Returns `REPRODUCES_DECLARED` if `(course_X, course_Y)` is in `all_declared_prereqs` (full set including held-out)
  - Returns `NOVEL` otherwise
- [ ] Implement `ReproductionClassifier.classify_all(edges, all_declared_prereqs) -> ReproductionReport`:
  - Counts and confidence distributions for each class
  - `ReproductionReport(reproduces_declared_count, novel_count, reproduces_declared_confidences: list[float], novel_confidences: list[float])`
- [ ] Write unit tests: edge whose course pair is in declared set → `REPRODUCES_DECLARED`; edge whose course pair is absent → `NOVEL`; empty input returns zero counts

---

## Task 6 — JudgementSetBuilder and rubric

**Implements:** REQ-EH-04, design §6

- [ ] Define `JudgementItem` dataclass: `item_id: str`, `concept_a_label: str`, `concept_a_course: str`, `concept_b_label: str`, `concept_b_course: str`, `knowledge_area: str`; no `is_inferred` field, no `confidence` field (blind)
- [ ] Define `JudgementSet` dataclass: `items: list[JudgementItem]`, `seed: int`, `sample_size: int`, `distractor_count: int`
- [ ] Implement `JudgementSetBuilder.build(novel_edges, all_concepts, sample_size, distractor_ratio, config) -> JudgementSet`:
  - Stratified sample of `sample_size` novel edges across knowledge areas (proportional)
  - Distractor generation: query pgvector for concept pairs with cosine similarity in [0.4, 0.6] that have no `DEPENDS_ON` edge; take `floor(sample_size * distractor_ratio)` distractors
  - Shuffle combined set with `random.Random(config.random_seed)`
  - Produce `JudgementSet` with no labels and no confidence values
- [ ] `JudgementSetBuilder.write_blind(judgement_set, store: ArtefactStore)` — writes `judgement_set_blind.json`
- [ ] `JudgementSetBuilder.write_rubric(store: ArtefactStore)` — writes `rubric.md` with the fixed rubric text from the design; rubric is written before any judgement item is shown
- [ ] Implement `JudgementAnalyser.load_labels(labelled_path: Path) -> LabelledJudgementSet` — reads expert labels from `judgement_set_labelled.json`; validates each item has a label from `{correct, plausible_but_wrong, incorrect}`
- [ ] Implement `JudgementAnalyser.analyse(labelled, original_edges) -> JudgementReport`:
  - Joins labels back to original `InferredEdge` confidence values (for inferred items only)
  - Computes approval rate (fraction `correct`) by confidence band
  - `JudgementReport(correct_count, plausible_but_wrong_count, incorrect_count, approval_by_confidence_band: dict[str, float])`
- [ ] Write unit tests: blind set contains no `is_inferred` or `confidence` fields; rubric file is written before blind set; stratified sampling spans at least 2 knowledge areas when input has edges from 3+

---

## Task 7 — FailureReporter

**Implements:** REQ-EH-06, design §7

- [ ] Implement `FailureReport` dataclass: `not_machine_checkable_rules: int`, `model_outputs_rejected: int`, `edges_removed_cycle_prevention: int`, `edges_rejected_ordering: int`, `poor_coverage_areas: list[str]`
- [ ] Implement `FailureReporter.collect(inference_summary, extraction_summary, ingestion_summary, ka_results, config) -> FailureReport`:
  - Reads failure counts from the JSON summaries produced by upstream pipeline runs
  - Populates `poor_coverage_areas` from `ka_results` where `poor_coverage == True`
  - All integer fields default to 0 if the upstream summary is absent (not None — always an int)
- [ ] Write unit tests: all fields present when all upstream summaries present; all fields zero (not absent) when no upstream summaries provided; `poor_coverage_areas` populated correctly from `KAMetricResult` list

---

## Task 8 — DepartmentFilterRegressionTest

**Implements:** REQ-EH-07, design §8

- [ ] Create `tests/test_department_filter.py` as a pytest test file
- [ ] Implement `find_cross_listed_cs_course(graph_client) -> CourseNode` — queries Neo4j for a `Course` with `subject_code == "CS"` that has at least one `CROSS_LISTING` `DeclaredEdge` to a course with a different subject code; raises `pytest.skip` if none found
- [ ] Implement `test_no_department_hard_filter(neo4j_client, config)`:
  - Calls `find_cross_listed_cs_course`
  - Runs `rerank(candidates, course=cross_listed, use_dept=True)` and `rerank(candidates, course=cross_listed, use_dept=False)`
  - Asserts `result_with_dept[0].ku_id == result_without_dept[0].ku_id`
- [ ] Add pytest marker `@pytest.mark.regression` to the test
- [ ] In `cli.py`: after `EvalRunner` completes, run `pytest tests/test_department_filter.py` as a subprocess; if it exits non-zero, print the output and exit the harness with code 2
- [ ] Write a unit test for `find_cross_listed_cs_course` using a mock graph client that returns a known cross-listed course

---

## Task 9 — AblationRunner

**Implements:** REQ-EH-05, design §4

- [ ] Define `PipelineMode` enum in `granular.inference` (if not already): `RETRIEVAL_ONLY`, `RETRIEVAL_RERANK`, `FULL_PIPELINE`
- [ ] Implement `AblationRunner.run_condition(split: Split, mode: PipelineMode, config: EvalConfig) -> MetricResult`:
  - Temporarily removes held-out edges from Neo4j (stores `edge_id` list, runs openCypher `MATCH (a)-[r:PREREQ {edge_id: $id}]->(b) DELETE r` for each)
  - Calls `granular-infer` subprocess with `--mode {mode}` flag
  - Reads inference output, runs `MetricCalculator.compute()`
  - Restores held-out edges to Neo4j (`MERGE` on `edge_id`)
  - Writes `ablation_{mode}.json` via `ArtefactStore`
- [ ] Implement `AblationRunner.run_all(split, config) -> AblationReport` — runs all three conditions, returns `AblationReport`
- [ ] Restoration is guaranteed even if the inference subprocess fails (try/finally around edge removal)
- [ ] Write unit tests for edge removal/restoration logic using a mock graph client; assert held-out edges are always restored even when `run_condition` raises

---

## Task 10 — ReportBuilder

**Implements:** REQ-EH-02 (breakdown), REQ-EH-08, design §9

- [ ] Implement `EvalReport` dataclass mirroring all report sections
- [ ] Implement `ReportBuilder.build(headline, by_area, ablation, reproduction, failures, config) -> EvalReport`
- [ ] Implement `ReportBuilder.to_json(report) -> dict` — machine-readable; all numeric fields present
- [ ] Implement `ReportBuilder.to_markdown(report, judgement_report=None) -> str`:
  - Section 1: scope statement generated from `config.institution`, `config.discipline`, `config.catalogue_year`, `config.ingestion_run_id` using the template from the design — never hand-written
  - Section 2: headline metric table (overall + high/medium/low bands)
  - Section 3: knowledge-area breakdown table; `poor_coverage_areas` flagged with `⚠`
  - Section 4: ablation comparison table (retrieval_only / retrieval_rerank / full_pipeline side by side)
  - Section 5: reproduction vs. contribution counts with confidence distributions
  - Section 6: failure report — all four failure counts always present, even if zero
  - Section 7: expert judgement summary — only rendered if `judgement_report` is not None
- [ ] Write unit tests: scope statement contains institution, discipline, catalogue year, and the portability caveat; failure section present even when all counts are zero; ablation table has exactly three rows

---

## Task 11 — EvalRunner and CLI

**Implements:** REQ-EH-09 (orchestration), design §11, CLI

- [ ] Implement `EvalRunner.run(config: EvalConfig, run_id: str)` following the orchestration sequence from the design exactly:
  1. `ArtefactStore.init_run(run_id)`
  2. `HeldOutSplit.load_or_create()` — loads existing split if `split.json` exists for this run_id, otherwise creates
  3. Remove held-out edges from Neo4j
  4. `AblationRunner.run_all()` → write ablation artefacts
  5. Restore held-out edges
  6. Run full inference pipeline subprocess
  7. `MetricCalculator.compute_all_bands()` and `compute_by_knowledge_area()`
  8. `ReproductionClassifier.classify_all()`
  9. `JudgementSetBuilder.build()` → write blind set + rubric
  10. `FailureReporter.collect()`
  11. `DepartmentFilterRegressionTest.run()` → exit 2 on failure
  12. `ReportBuilder.build()` → write `report.json` + `report.md`
  13. `ArtefactStore.finalise_manifest()` → write `manifest.json`
- [ ] Implement `cli.py` with `typer` (or `argparse`) exposing commands: `run`, `split`, `metric`, `judge`, `report`
- [ ] `run` command: `--config PATH`, `--run-id ID` (default: new UUID4), `--artefact-dir PATH`
- [ ] `split` command: create held-out split only; write `split.json` and exit
- [ ] `metric` command: compute metric against an existing run's inference snapshot; `--run-id` required
- [ ] `judge` command: load `judgement_set_labelled.json`, run `JudgementAnalyser`, re-render report with judgement section; `--run-id` required
- [ ] `report` command: re-render `report.md` from existing `report.json`; `--run-id` required
- [ ] Register `granular-eval` as a console script in `pyproject.toml`
- [ ] Write integration test: mock Neo4j client + mock inference subprocess; run `EvalRunner.run()`; assert manifest exists, report contains all sections, held-out edges restored after run

---

## Task 12 — Package wiring and pyproject.toml entry

**Implements:** packaging, dependency declarations

- [ ] Add `granular.evaluation` to the package list in `pyproject.toml`
- [ ] Add dependencies: `neo4j`, `scipy`, `pytest`, `typer` (or `argparse`), `tomllib` (stdlib ≥ 3.11)
- [ ] Add `granular-eval` console script entry point pointing to `granular.evaluation.cli:app`
- [ ] Confirm `granular.evaluation` imports cleanly with `python -c "import granular.evaluation"`
- [ ] Add `data/evaluation/runs/` to `.gitignore` (already present — verify)
