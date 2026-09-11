# Tasks — evaluation-harness

## Prerequisites

These specs must be complete before any task in this spec can be implemented:

- `canonical-schema` — `InferredEdge`, `DeclaredEdge`, `SchemaValidationError`
- `concept-graph-inference` — `ConceptGraphSnapshot`, `PipelineMode` flag, `InferenceSummary`

---

## Status

All 12 tasks have an implementation in `src/granular/evaluation/` with passing tests
(`uv run pytest tests/evaluation/ -q` → 45 passed). Tasks 1, 4, 5, 7, 10, 12 match the
design as written. Tasks 2, 3, 6, 8, 9, 11 shipped with deliberate or notable deviations
from the original design — see the "adapted" / "partially done" notes on each task below.
The two biggest gaps from the original design:

- **No live Neo4j edge removal/restoration for ablation.** `AblationRunner` reruns
  dependency inference in-memory per `PipelineMode` instead of deleting/restoring
  held-out edges in the graph and shelling out to `granular-infer` (Task 9).
- **`EvalRunner.run()` doesn't run the full orchestration.** It skips the department-filter
  regression gate, judgement-set generation, and real per-condition ablation (those are
  either separate CLI commands or not wired in yet) (Task 11).

---

## Task 1 — Package scaffold and EvalConfig ✅ DONE

**Implements:** design §1 (EvalConfig), package layout

- [x] Create `src/granular/evaluation/` package with `__init__.py`
- [x] Implement `EvalConfig` dataclass in `config.py` with all fields from the design: `neo4j_uri`, `neo4j_user`, `neo4j_password`, `held_out_fraction` (default 0.20), `random_seed` (default 42), `min_f1_poor_threshold` (default 0.40), `confidence_high` (default 0.70), `confidence_medium_low` (default 0.40), `distractor_ratio` (default 1.0), `institution`, `discipline`, `catalogue_year`, `ingestion_run_id`, `output_dir`, `artefact_dir`
- [x] Implement `EvalConfig.from_toml(path: Path) -> EvalConfig` loading from a TOML file
- [x] Implement `EvalConfig.from_env() -> EvalConfig` reading `NEO4J_*` / `GRANULAR_*` environment variables as overrides
- [x] Add `__post_init__` validator: `held_out_fraction` must be in (0, 1); `random_seed` must be a non-negative int; `confidence_high` > `confidence_medium_low`
- [x] Create `data/evaluation/runs/.gitkeep` so the directory is tracked
- [x] Write unit tests for `EvalConfig` validation (valid config, each invalid field) — *no test exercises `from_toml`/`from_env` directly*

---

## Task 2 — ArtefactStore ⚠️ MOSTLY DONE

**Implements:** REQ-EH-09, design §10

- [x] Implement `ArtefactStore` in `artefacts.py`
- [x] `init_run(run_id: str) -> Path` — creates `{artefact_dir}/{run_id}/` directory; raises if it already exists unless `resume=True`
- [x] `write(name: str, data: dict | str) -> Path` — writes `{name}.json` (dict) or `{name}.md` (str) to the run directory; records filename and `written_at` in an internal manifest list
- [x] `finalise_manifest() -> Path` — computes sha256 checksum for every written file; writes `manifest.json` with `[{filename, sha256, written_at}]`
- [x] Artefact filenames include the run_id prefix: `{run_id}_{name}.json`
- [ ] Write unit tests: write multiple artefacts, call `finalise_manifest`, assert manifest contains correct checksums (done); assert re-writing an existing artefact raises — **not implemented**: `write()` has no duplicate-name guard, so this case is untested

---

## Task 3 — HeldOutSplit ⚠️ MOSTLY DONE (adapted)

**Implements:** REQ-EH-01, design §2

- [x] Implement `Split` dataclass in `split.py`: `train: list[str]`, `test: list[str]`, `seed: int`, `fraction: float`, `ingestion_run_id: str`, `created_at: str` (ISO timestamp)
- [x] Implement `HeldOutSplit.create(...) -> Split` — *signature differs from design*: takes `prereq_keys: list[str]` (`"course->prereq_course"` strings) rather than `list[DeclaredEdge]`; the course-pair keys are derived by the caller from declared prerequisites
  - [x] Shuffles with `random.Random(config.random_seed)`
  - [x] Takes last `floor(len * held_out_fraction)` as test set
  - [x] Records `ingestion_run_id` and `created_at` from config
  - [ ] Writes `split.json` via `ArtefactStore.write()` — not done inside `create()`; the caller (`EvalRunner`) writes it instead
  - [x] Returns `Split`
- [x] Implement `HeldOutSplit.load(path: Path) -> Split` — deserialises from JSON; validates required fields present
- [ ] Add guard: raise `RuntimeError` if the split file already exists for this run_id — **not implemented** (`create()` never touches the filesystem, so there is nothing to guard)
- [x] Write unit tests: fixed seed produces identical split across two calls; fraction is respected within ±1 edge; train/test disjoint; round-trip serialise/deserialise preserves metadata

---

## Task 4 — MetricCalculator ✅ DONE

**Implements:** REQ-EH-02, design §3

- [x] Implement `MetricResult` dataclass: `precision`, `recall`, `f1`, `tp`, `fp`, `fn`, `confidence_filter: Optional[str]`
- [x] Implement `KAMetricResult` dataclass: `knowledge_area`, `knowledge_area_label`, `precision`, `recall`, `f1`, `sample_size`, `poor_coverage: bool`
- [x] Implement `MetricCalculator.compute(held_out, graph, all_declared, confidence_filter=None) -> MetricResult`:
  - For each held-out (course X, course Y) pair: BFS (max depth 5) over `DEPENDS_ON`-style edges restricted to concepts from Y, checking for a path reaching any concept from X → TP
  - Held-out pairs with no such path → FN
  - Inferred course-pair paths not in any declared prerequisite set → FP
  - Compute precision = TP / (TP + FP), recall = TP / (TP + FN), F1 = harmonic mean
  - When `confidence_filter` is set (`"high"`, `"medium"`, `"low"`), restrict the adjacency to edges in the corresponding confidence band
- [x] Implement `MetricCalculator.compute_by_knowledge_area(...) -> list[KAMetricResult]`:
  - Group held-out edges by the knowledge area of the concepts in the prerequisite course
  - Compute `MetricResult` per group
  - Set `poor_coverage = f1 < poor_threshold`
- [x] Implement `MetricCalculator.compute_all_bands(...) -> dict[str, MetricResult]` — runs `compute()` for `None`/`"all"`, `"high"`, `"medium"`, `"low"` and returns all four
- [x] Write unit tests: perfect recall (all held-out paths present), zero recall (no paths), confidence-band filter, all-bands, by-knowledge-area — *no dedicated test for the BFS max-depth cutoff*

---

## Task 5 — ReproductionClassifier ✅ DONE

**Implements:** REQ-EH-03, design §5

- [x] Implement `EdgeClass` enum: `REPRODUCES_DECLARED`, `NOVEL`
- [x] Implement `ReproductionClassifier.classify(from_concept, to_concept) -> EdgeClass`:
  - Resolves concepts to their source course IDs via the concept graph
  - Returns `REPRODUCES_DECLARED` if `(course_X, course_Y)` is in `all_declared_prereqs` (full set including held-out)
  - Returns `NOVEL` otherwise
- [x] Implement `ReproductionClassifier.classify_all() -> ReproductionReport`:
  - Counts and confidence distributions for each class
  - `ReproductionReport(reproduces_declared_count, novel_count, reproduces_declared_confidences: list[float], novel_confidences: list[float])`
- [x] Write unit tests: edge whose course pair is in declared set → `REPRODUCES_DECLARED`; edge whose course pair is absent → `NOVEL`; counts aggregate correctly across a set of edges

---

## Task 6 — JudgementSetBuilder and rubric ⚠️ MOSTLY DONE (adapted)

**Implements:** REQ-EH-04, design §6

- [x] Define `JudgementItem` dataclass: `item_id`, `concept_a_label`, `concept_a_course`, `concept_b_label`, `concept_b_course`, `knowledge_area`; no `is_inferred` field, no `confidence` field (blind)
- [x] Define `JudgementSet` dataclass: `items: list[JudgementItem]`, `seed: int`, `sample_size: int`, `distractor_count: int`
- [x] Implement `JudgementSetBuilder.build(novel_edges, distractors, sample_size, distractor_ratio, config) -> JudgementSet`:
  - Stratified sample of `sample_size` novel edges across knowledge areas (proportional)
  - [ ] Distractor generation via pgvector cosine-similarity query — **not implemented**: `build()` takes a pre-supplied `distractors: list[CandidateEdge]` instead of querying pgvector itself; the caller is responsible for sourcing them
  - Shuffle combined set with `random.Random(config.random_seed)`
  - Produce `JudgementSet` with no labels and no confidence values
- [x] `JudgementSetBuilder.write_blind(judgement_set, store: ArtefactStore)` — writes `judgement_set_blind.json`
- [x] `JudgementSetBuilder.write_rubric(store: ArtefactStore)` — writes `rubric.md` with fixed rubric text; rubric is written before any judgement item is shown
- [x] Implement `JudgementAnalyser.load_labels(labelled_path: Path) -> dict[str, str]` — reads expert labels from `judgement_set_labelled.json`; validates each item has a label from `{correct, plausible_but_wrong, incorrect}`
- [x] Implement `JudgementAnalyser.analyse(labels, candidates, config) -> JudgementReport`:
  - Joins labels back to candidate confidence values (for inferred items only)
  - Computes approval rate (fraction `correct`) by confidence band
  - `JudgementReport(correct_count, plausible_but_wrong_count, incorrect_count, approval_by_confidence_band: dict[str, float])`
- [x] Write unit tests: blind set contains no `is_inferred` or `confidence` fields; rubric file is written before blind set; stratified sampling spans at least 2 knowledge areas; label validation rejects invalid labels; approval-by-confidence-band computed correctly

---

## Task 7 — FailureReporter ✅ DONE

**Implements:** REQ-EH-06, design §7

- [x] Implement `FailureReport` dataclass: `not_machine_checkable_rules: int`, `model_outputs_rejected: int`, `edges_removed_cycle_prevention: int`, `edges_rejected_ordering: int`, `poor_coverage_areas: list[str]`
- [x] Implement `FailureReporter.collect(inference_summary, extraction_summary, ingestion_summary, ka_results) -> FailureReport`:
  - Reads failure counts from the JSON summaries produced by upstream pipeline runs (plus a `load_summary()` helper to read them from disk, returning `None` if absent)
  - Populates `poor_coverage_areas` from `ka_results` where `poor_coverage == True`
  - All integer fields default to 0 if the upstream summary is absent (not None — always an int)
- [x] Write unit tests: all fields present/summed correctly when upstream summaries present; all fields zero (not absent) when no upstream summaries provided; `poor_coverage_areas` populated correctly from `KAMetricResult` list

---

## Task 8 — DepartmentFilterRegressionTest ⚠️ MOSTLY DONE (adapted, not wired into CLI)

**Implements:** REQ-EH-07, design §8

- [x] Create `tests/evaluation/test_department_filter.py` as a pytest test file (different path than spec's `tests/test_department_filter.py`)
- [ ] Implement `find_cross_listed_cs_course(graph_client)` querying Neo4j — **not implemented**: the test builds a fixed cross-listed `Course` fixture in-process (`make_cross_listed_course()`) instead of querying a live graph
- [x] Implement `test_no_department_hard_filter()` (adapted signature, no `neo4j_client`/`config` fixtures):
  - Builds a cross-listed CS/ECE course and candidate KUs directly
  - Runs `rerank(...)` with the default department-prior weight and with `weight_department_prior=0.0` (in place of a `use_dept` flag)
  - Asserts the top-ranked candidate's `ku_id` is identical in both cases, and that no candidate is dropped
- [x] Add pytest marker `@pytest.mark.regression` to the test
- [ ] In `cli.py`: run this test as a subprocess after `EvalRunner` completes, exiting the harness with code 2 on failure — **not implemented**; the regression test is not invoked from `EvalRunner.run()` or `cli.py`
- [ ] Unit test for `find_cross_listed_cs_course` with a mock graph client — **not applicable**, since that function doesn't exist

---

## Task 9 — AblationRunner ⚠️ DONE VIA DIFFERENT MECHANISM

**Implements:** REQ-EH-05, design §4

- [x] `PipelineMode` enum already existed in `granular.inference.config`: `RETRIEVAL_ONLY`, `RETRIEVAL_RERANK`, `FULL_PIPELINE`
- [x] Implement `AblationRunner.run_condition(mode, held_out, all_declared) -> MetricResult` — **implemented differently from the design**: instead of mutating Neo4j and shelling out to `granular-infer`, it calls an injected `infer_fn(mode) -> InferredGraph` that reruns dependency inference *in-memory* for that mode (see `build_ablation_infer_fn` in `ablation.py`), then runs `MetricCalculator.compute()` against the result. This avoids live edge deletion/restoration entirely.
  - [ ] Neo4j edge removal (`DELETE`) / restoration (`MERGE`) around the run — **not implemented** (not needed by the in-memory approach)
  - [ ] `granular-infer` subprocess call — **not implemented**; real ablation is exposed as its own `granular-eval ablation` CLI command (`cli.py`) rather than being invoked per-condition from within `AblationRunner`
  - [ ] Writes `ablation_{mode}.json` via `ArtefactStore` — done by the `ablation` CLI command (writes a combined `ablation.json`), not by `AblationRunner` itself
- [x] Implement `AblationRunner.run_all(held_out, all_declared) -> AblationReport` — runs all three conditions, returns `AblationReport`
- [ ] try/finally-guaranteed restoration — **not applicable**; no live graph mutation occurs
- [x] Write unit tests: `run_all` behaves correctly across a mocked `infer_fn` (full-pipeline recovers, degraded mode does not) — no edge removal/restoration test exists since that mechanism isn't used

---

## Task 10 — ReportBuilder ✅ DONE

**Implements:** REQ-EH-02 (breakdown), REQ-EH-08, design §9

- [x] Implement `EvalReport` dataclass mirroring all report sections
- [x] Implement `ReportBuilder.build(headline, by_area, ablation, reproduction, failures, config) -> EvalReport`
- [x] Implement `ReportBuilder.to_json(report) -> dict` — machine-readable; all numeric fields present
- [x] Implement `ReportBuilder.to_markdown(report, judgement_report=None) -> str`:
  - Section 1: scope statement generated from `config.institution`, `config.discipline`, `config.catalogue_year`, `config.ingestion_run_id` via a fixed template (includes the genericity/portability caveat) — never hand-written
  - Section 2: headline metric table (all + high/medium/low bands)
  - Section 3: knowledge-area breakdown table; `poor_coverage` areas flagged with `⚠`
  - Section 4: ablation comparison table (retrieval_only / retrieval_rerank / full_pipeline side by side)
  - Section 5: reproduction vs. contribution counts
  - Section 6: failure report — all four failure counts always present, even if zero
  - Section 7: expert judgement summary — only rendered if `judgement_report` is not None
- [x] Write unit tests: scope statement contains institution, discipline, catalogue year, and the portability caveat; all markdown sections present; failure section present even when all counts are zero; ablation table has exactly three rows

---

## Task 11 — EvalRunner and CLI ⚠️ PARTIALLY DONE (simplified orchestration)

**Implements:** REQ-EH-09 (orchestration), design §11, CLI

- [ ] Implement `EvalRunner.run(config, run_id)` following the 13-step orchestration sequence from the design exactly — **implemented as a simplified sequence**, via `EvalRunner(config, graph_loader).run(run_id)`:
  1. [x] `ArtefactStore.init_run(run_id)`
  2. [x] Builds the held-out split from the injected graph loader's declared prereqs (no persisted-split reuse / `load_or_create` semantics)
  3. [ ] Remove held-out edges from Neo4j — **not done**; no live graph mutation
  4. [ ] `AblationRunner.run_all()` inline — **not done**: `run()` fabricates the ablation section by repeating the full-pipeline metric for all three conditions; real per-mode ablation only happens via the separate `granular-eval ablation` CLI command (Task 9)
  5. [ ] Restore held-out edges — not applicable (nothing was removed)
  6. [ ] Run full inference pipeline subprocess — **not done**; the graph is supplied by the injected `graph_loader` instead
  7. [x] `MetricCalculator.compute_all_bands()` and `compute_by_knowledge_area()`
  8. [x] `ReproductionClassifier.classify_all()`
  9. [ ] `JudgementSetBuilder.build()` → write blind set + rubric — **not wired into `EvalRunner.run()`**; `JudgementSetBuilder`/`JudgementAnalyser` exist (Task 6) but are not called from the orchestration
  10. [x] `FailureReporter.collect()` (reads upstream summaries from `data/{inference,extraction,ingestion}/output/summary.json` if present)
  11. [ ] Department-filter regression gate with exit code 2 — **not implemented** (see Task 8)
  12. [x] `ReportBuilder.build()` → write `report.json` + `report_md.md`
  13. [x] `ArtefactStore.finalise_manifest()` → write `manifest.json`
- [x] Implement `cli.py` with `typer` — commands actually exposed: `run`, `ablation`, `alignment`, `discover`, `split`
  - [x] `run`: `--config`, `--run-id`, `--artefact-dir` — runs `EvalRunner` end-to-end against a live Neo4j-backed loader
  - [x] `ablation`: real per-mode ablation (in-memory rerun), writes `ablation.json` — not in the original task list, added to cover Task 9's actual mechanism
  - [ ] `split` command: create held-out split only, write `split.json`, exit — **stub only**; currently just prints a message telling the user to run `run` instead
  - [ ] `metric` command — **not implemented**
  - [ ] `judge` command — **not implemented**
  - [ ] `report` command — **not implemented**
  - [x] `alignment`, `discover`: additional eval commands (alignment-precision, discover-relevance) built beyond the original spec — see `alignment_eval.py` / `discover_eval.py`
- [x] Register `granular-eval` as a console script in `pyproject.toml`
- [ ] Write integration test: mock Neo4j client + mock inference subprocess; run `EvalRunner.run()`; assert manifest exists, report contains all sections, held-out edges restored after run — **partially done**: `test_full_run_produces_report` (in `test_ablation_report_runner.py`) uses a mock graph loader and asserts the manifest/report/report-md artefacts exist and the result has `scope_statement`/`headline`; it does not mock a Neo4j client or inference subprocess, and there is no edge-restoration assertion since no edges are ever removed

---

## Task 12 — Package wiring and pyproject.toml entry ✅ DONE

**Implements:** packaging, dependency declarations

- [x] `granular.evaluation` is covered by the `packages = ["src/granular"]` entry in `pyproject.toml`
- [x] Dependencies present: `neo4j`, `scipy`, `pytest`, `typer`; `tomllib` used directly (stdlib ≥ 3.11, no dependency needed)
- [x] `granular-eval` console script entry point registered, pointing to `granular.evaluation.cli:app`
- [x] Confirmed `granular.evaluation` imports cleanly with `python -c "import granular.evaluation"`
- [x] `data/evaluation/runs/` and `data/evaluation/output/` present in `.gitignore`
