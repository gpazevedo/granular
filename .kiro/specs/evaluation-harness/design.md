# Design — evaluation-harness

## Overview

The evaluation harness is a Python package (`granular.evaluation`) and CLI tool (`granular-eval`) that measures the quality of the inference pipeline. It operates on the Neo4j graph produced by `concept-graph-inference` and the declared edges from `catalogue-ingestion`. It produces a structured report with the headline metric, ablation results, failure counts, and a scope statement.

The harness has no side effects on the live graph. It reads Neo4j but never writes to it during evaluation. All outputs go to a versioned artefact directory.

---

## Package layout

```text
src/
  granular/
    evaluation/
      __init__.py
      cli.py                      # granular-eval entry point
      config.py                   # EvalConfig
      split.py                    # HeldOutSplit — create and persist the train/test split
      metric.py                   # MetricCalculator — precision, recall, F1
      ablation.py                 # AblationRunner — reruns pipeline under restricted conditions
      judge.py                    # JudgementSetBuilder — novel edge sampling + distractor mixing
      report.py                   # ReportBuilder — assembles final JSON + Markdown report
      artefacts.py                # ArtefactStore — versioned file management + manifest
      runner.py                   # EvalRunner — top-level orchestration
data/
  evaluation/
    runs/
      {run_id}/                   # one directory per eval run
        split.json
        inference_snapshot.json
        ablation_{condition}.json
        judgement_set_blind.json
        judgement_set_labelled.json    # written after expert judgement
        report.json
        report.md
        manifest.json
```

---

## Component breakdown

### 1. EvalConfig

```python
@dataclass
class EvalConfig:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    held_out_fraction: float        # default: 0.20
    random_seed: int                # default: 42
    min_f1_poor_threshold: float    # default: 0.40
    confidence_high: float          # default: 0.70
    confidence_medium_low: float    # default: 0.40
    distractor_ratio: float         # default: 1.0 (equal distractors to inferred)
    institution: str                # default: "Purdue University"
    discipline: str                 # default: "Computer Science"
    catalogue_year: str             # e.g. "2026-2027"
    ingestion_run_id: str           # traceable to a specific data snapshot
    output_dir: Path
    artefact_dir: Path
```

---

### 2. HeldOutSplit

Creates and persists the train/test split before any inference runs. Must be called before `granular-infer` in a fresh evaluation cycle.

```python
class HeldOutSplit:
    def create(self, declared_edges: list[DeclaredEdge], config: EvalConfig) -> Split: ...
    def load(self, path: Path) -> Split: ...
```

Algorithm:

1. Load all `DeclaredEdge(PREREQUISITE)` records from Neo4j
2. Shuffle with `random.Random(config.random_seed)`
3. Take the last `floor(len * held_out_fraction)` as the held-out test set
4. Write both sets to `split.json` with metadata (seed, fraction, ingestion_run_id, created_at)
5. Return a `Split(train: list[DeclaredEdge], test: list[DeclaredEdge])`

The train set is what the inference pipeline sees. The test set is withheld from Neo4j (the runner temporarily removes these edges before calling `granular-infer`, then restores them after). This is managed by the `EvalRunner`, not the inference pipeline itself.

```python
@dataclass
class Split:
    train: list[str]      # edge_ids
    test:  list[str]      # edge_ids
    seed:  int
    fraction: float
    ingestion_run_id: str
    created_at: datetime
```

---

### 3. MetricCalculator

Computes precision, recall, and F1 at the **course-pair level**:

- **True positive**: a withheld declared prerequisite (course X requires course Y) for which the inferred concept graph contains at least one directed `DEPENDS_ON` path from a concept in Y to a concept in X.
- **False negative**: a withheld pair with no such path.
- **False positive**: an inferred concept dependency path between courses X and Y where X→Y was not a declared (or withheld) prerequisite.

```python
class MetricCalculator:
    def compute(
        self,
        held_out: list[DeclaredEdge],
        inferred_graph: ConceptGraphSnapshot,
        confidence_filter: Optional[tuple[float, float]] = None,
    ) -> MetricResult: ...

    def compute_by_knowledge_area(
        self,
        held_out: list[DeclaredEdge],
        inferred_graph: ConceptGraphSnapshot,
    ) -> list[KAMetricResult]: ...
```

Path detection uses BFS (max depth 5) over the inferred `DEPENDS_ON` subgraph restricted to `concept_id`s belonging to the relevant courses.

```python
@dataclass
class MetricResult:
    precision: float
    recall:    float
    f1:        float
    tp:        int
    fp:        int
    fn:        int
    confidence_filter: Optional[str]   # "high", "medium", "low", None

@dataclass
class KAMetricResult:
    knowledge_area: str
    knowledge_area_label: str
    precision: float
    recall:    float
    f1:        float
    sample_size: int        # held-out edges in this area
    poor_coverage: bool     # f1 < min_f1_poor_threshold
```

---

### 4. AblationRunner

Reruns the dependency inference pipeline under three restricted conditions against the same held-out split:

| Condition | Description |
| --- | --- |
| `retrieval_only` | Stage 1 only (embedding similarity). Skips reranking, structural rejection. Uses raw similarity score as confidence. |
| `retrieval_rerank` | Stages 1–2. Applies metadata reranking but no structural rejection. |
| `full_pipeline` | All stages 1–4 (normal run). |

Each condition is implemented by passing a `PipelineMode` flag to the inference pipeline, which short-circuits at the appropriate stage. The ablation runner:

1. Removes held-out edges from Neo4j (same as the main eval)
2. Runs inference under the specified condition
3. Computes `MetricResult` for that condition
4. Restores held-out edges
5. Writes the inference snapshot and metric to `ablation_{condition}.json`

```python
class AblationRunner:
    def run_all(self, split: Split, config: EvalConfig) -> AblationReport: ...

@dataclass
class AblationReport:
    retrieval_only:    MetricResult
    retrieval_rerank:  MetricResult
    full_pipeline:     MetricResult
```

---

### 5. ReproductionClassifier

Classifies each inferred `DEPENDS_ON` edge as `reproduces_declared` or `novel`:

```python
def classify(edge: InferredEdge, all_declared_prereqs: set[tuple[str, str]]) -> EdgeClass:
```

An edge from concept A (course X) to concept B (course Y) is `reproduces_declared` if `(X, Y)` is in the full declared prerequisite set (including the held-out portion, after evaluation). Otherwise `novel`.

Both classes are reported with count and confidence distribution in the final report.

---

### 6. JudgementSetBuilder

Generates a blinded set for expert judgement of novel edges.

```python
class JudgementSetBuilder:
    def build(
        self,
        novel_edges: list[InferredEdge],
        all_concepts: list[ConceptNode],
        sample_size: int,
        distractor_ratio: float,
        config: EvalConfig,
    ) -> JudgementSet: ...
```

Steps:

1. Sample `sample_size` novel inferred edges, stratified by knowledge area
2. Generate `floor(sample_size * distractor_ratio)` distractors: concept pairs with moderate pgvector cosine similarity (0.4–0.6) that have no inferred edge — plausible but not asserted
3. Shuffle combined set with a fixed seed
4. Write `judgement_set_blind.json` — items listed with concept labels and course context, no inferred/distractor label, no confidence score visible

The rubric is written to `rubric.md` before any judgement:

```markdown
## Judgement rubric

For each item, assess whether concept A depends on concept B
(i.e. understanding B is necessary to understand A):

- correct: the dependency is real and directionally accurate
- plausible_but_wrong: dependency exists but direction is reversed, or the
  relationship is similarity rather than dependency
- incorrect: no meaningful dependency exists between these concepts
```

After expert judgement, labels are written to `judgement_set_labelled.json` and the `JudgementAnalyser` computes agreement between expert labels and pipeline confidence bands.

---

### 7. FailureReporter

Aggregates all failure counts from the pipeline runs:

```python
@dataclass
class FailureReport:
    not_machine_checkable_rules:     int
    model_outputs_rejected:          int   # from concept-extraction
    edges_removed_cycle_prevention:  int
    edges_rejected_ordering:         int
    poor_coverage_areas:             list[str]   # KA labels where F1 < threshold
```

All fields are always present. A count of zero is reported explicitly, never omitted.

---

### 8. DepartmentFilterRegressionTest

A standalone pytest test included in the harness test suite. Locates at least one cross-listed CS course in the Neo4j graph, runs the alignment pipeline's reranking stage with and without the department signal zeroed out, and asserts that the top-ranked candidate does not change when department is removed — confirming department is never a deciding filter.

```python
def test_no_department_hard_filter(neo4j_client, config):
    cross_listed = find_cross_listed_cs_course(neo4j_client)
    result_with_dept    = rerank(candidates, course=cross_listed, use_dept=True)
    result_without_dept = rerank(candidates, course=cross_listed, use_dept=False)
    assert result_with_dept[0].ku_id == result_without_dept[0].ku_id
```

Test failure causes `granular-eval` to exit with code 2.

---

### 9. ReportBuilder

Assembles the final report from all components:

```python
class ReportBuilder:
    def build(
        self,
        headline: MetricResult,
        by_area: list[KAMetricResult],
        ablation: AblationReport,
        reproduction: dict,
        failures: FailureReport,
        config: EvalConfig,
    ) -> EvalReport: ...
```

Produces both `report.json` (machine-readable) and `report.md` (human-readable). The Markdown report includes:

1. Scope statement (generated from config — not hand-written)
2. Headline metric table (overall + by confidence band)
3. Knowledge-area breakdown table (F1 per area, poor-coverage areas flagged)
4. Ablation comparison table
5. Reproduction vs. contribution counts
6. Failure report
7. Expert judgement summary (if labelled set exists)

**Scope statement template** (generated, not written manually):

```text
This evaluation covers {institution} ({discipline}) courses from the
{catalogue_year} catalogue (ingestion run {ingestion_run_id}).
The genericity claim covers adapter genericity across the Modern Campus
Acalog platform. Extraction genericity across disciplines has not been tested.
```

---

### 10. ArtefactStore

```python
class ArtefactStore:
    def init_run(self, run_id: str) -> Path: ...       # creates run directory
    def write(self, name: str, data: dict) -> Path: ...
    def finalise_manifest(self) -> None: ...           # checksums all files
```

Each file is named `{name}.json` or `{name}.md` inside `{artefact_dir}/{run_id}/`. The manifest records filename, sha256 checksum, and written_at for every artefact.

---

### 11. EvalRunner

Top-level orchestration:

```text
EvalConfig.load()
ArtefactStore.init_run(run_id)
HeldOutSplit.load_or_create()
→ remove held-out edges from Neo4j (temporarily)
AblationRunner.run_all()          → ablation_{condition}.json
→ restore held-out edges
→ run full inference pipeline     → final graph
MetricCalculator.compute()        → headline metric
MetricCalculator.compute_by_ka()  → per-area breakdown
ReproductionClassifier.classify() → reproduction report
JudgementSetBuilder.build()       → judgement_set_blind.json + rubric.md
FailureReporter.collect()         → failure report
DepartmentFilterRegressionTest.run() → exit 2 on failure
ReportBuilder.build()             → report.json + report.md
ArtefactStore.finalise_manifest() → manifest.json
```

---

## CLI

```text
granular-eval [OPTIONS] COMMAND

Commands:
  run          Full evaluation run (split + ablation + metric + report)
  split        Create held-out split only (run before granular-infer)
  metric       Compute metric against existing inference output
  judge        Load a completed judgement set and update the report
  report       Re-render report from existing artefacts

Options:
  --config PATH
  --run-id ID      Resume or reference a specific run (default: new UUID)
  --artefact-dir PATH
```

---

## Dependencies

- `neo4j` Python driver
- `pytest` — department regression test
- `scipy` — confidence distribution stats
- `granular.schema`
- `granular.inference` — imported for ablation reruns (PipelineMode flag)

## openCypher portability note

All graph reads in this package use openCypher syntax. No APOC or GDS procedures are called. The harness reads Neo4j but never writes to the live graph during evaluation, so it is safe to run against any openCypher-compatible store.
