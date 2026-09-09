# Design — concept-extraction

## Overview

The concept-extraction pipeline is a Python package (`granular.extraction`) that runs in two phases:

1. **Bootstrap** (one-time, manual): extracts CS2023 knowledge areas and knowledge units from the published PDF and writes a versioned seed file.
2. **Extraction + alignment** (run after ingestion): for each ingested `Course`, extracts atomic concepts from the description and aligns each concept to a CS2023 `KnowledgeUnit` via a four-stage pipeline.

Embeddings are stored in pgvector. All alignment decisions are stored in Neo4j as `Concept` nodes and `InferredEdge(CONCEPT_MEMBERSHIP)` edges. The pipeline is a CLI tool (`granular-extract`).

---

## Package layout

```text
src/
  granular/
    extraction/
      __init__.py
      cli.py                    # granular-extract entry point
      config.py                 # ExtractionConfig
      bootstrap/
        __init__.py
        pdf_parser.py           # CS2023PdfParser → list[KnowledgeUnit]
        seed_writer.py          # writes data/cs2023_vocabulary.json
      extractor.py              # ConceptExtractor — LLM call → list[RawConcept]
      embedder.py               # Embedder — text → vector, pgvector store
      pipeline/
        __init__.py
        retrieve.py             # Stage 1: top-k KU candidates from pgvector
        rerank.py               # Stage 2: metadata reranking
        reject.py               # Stage 3: structural rejection
        verify.py               # Stage 4: constrained selection
      aligner.py                # Aligner — runs stages 1-4 per concept
      coverage.py               # CoverageIndex — thin-coverage queries
      runner.py                 # ExtractionRunner — orchestrates per-course
      summary.py                # ExtractionSummary dataclass + JSON writer
data/
  cs2023_vocabulary.json        # versioned seed file (committed)
```

---

## Component breakdown

### 1. CS2023 Bootstrap

#### CS2023PdfParser

Uses `pdfplumber` to extract text from the CS2023 PDF. The CS2023 document has a consistent structure: knowledge areas appear as top-level sections with a two-to-three letter code (e.g. `AL` — Algorithms and Complexity), and knowledge units are subsections within each area, each with a label, tier classification (Core/Elective), and hour allocation.

Extraction strategy:

- Detect knowledge area headers by regex: all-caps codes followed by em-dash and title
- Within each area, detect knowledge unit entries by indentation level and bullet structure
- Extract tier from explicit "Core" / "Elective" labels in the text
- Extract contact hours from numeric patterns adjacent to tier labels

Output: `list[KnowledgeUnit]` conforming to the canonical schema.

If a page range cannot be parsed, the parser logs `(page_start, page_end, reason)` and continues. The final count is reported.

#### SeedWriter

Writes the extracted `KnowledgeUnit` list to `data/cs2023_vocabulary.json` with a metadata header:

```json
{
  "source": "CS2023",
  "extracted_at": "2026-09-08T...",
  "knowledge_area_count": 17,
  "knowledge_unit_count": 132,
  "units": [ ... ]
}
```

This file is committed to the repository and loaded by the extraction pipeline at startup. It is never regenerated automatically during pipeline runs.

---

### 2. ExtractionConfig

```python
@dataclass
class ExtractionConfig:
    vocabulary_path: Path         # default: data/cs2023_vocabulary.json
    llm_model_id: str             # e.g. "openai/gpt-4o-mini"
    embedding_model_id: str       # e.g. "openai/text-embedding-3-small"
    top_k: int                    # retrieval candidate count, default: 10
    min_confidence: float         # default: 0.3
    low_confidence_threshold: float  # default: 0.5
    min_description_length: int   # default: 20 chars
    pgvector_dsn: str
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    output_dir: Path
    summary_path: Path
    adapter_name: str
    adapter_version: str
```

---

### 3. ConceptExtractor

Makes a single structured LLM call per course to extract atomic concept labels from the course description.

**Prompt design:** the system prompt instructs the model to extract only concepts explicitly stated or strongly implied in the description, at the grain of CS2023 knowledge units (examples of correct grain are given). It explicitly forbids inferring from course title or number. It returns a JSON array of `{"label": str}` objects.

**Why one call per course:** keeps the prompt focused, makes retry/failure isolated to one course, and keeps token cost proportional to description length.

Output: `list[RawConcept]`:

```python
@dataclass
class RawConcept:
    label: str
    source_course_id: str
    model_id: str
```

Failure handling: if the LLM returns malformed JSON or an empty array for a non-empty description, the extractor logs the failure and returns an empty list for that course (no `Concept` records produced). This counts as a failed extraction in the summary.

---

### 4. Embedder

Wraps the embedding model API. Stores vectors in pgvector via `psycopg2`.

Schema (pgvector table):

```sql
CREATE TABLE IF NOT EXISTS embeddings (
    id          TEXT PRIMARY KEY,   -- concept_id or ku_id
    entity_type TEXT NOT NULL,      -- 'concept' or 'knowledge_unit'
    label       TEXT NOT NULL,
    vector      vector(1536),       -- dimension from config
    model_id    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON embeddings USING ivfflat (vector vector_cosine_ops);
```

**Critical invariant:** only the bare label text is embedded. No course number, department, or level metadata is concatenated into the embedded string. Metadata is used exclusively at the reranking stage.

On bootstrap, all `KnowledgeUnit` labels are embedded and stored with `entity_type = 'knowledge_unit'`.

---

### 5. Alignment Pipeline — Stage 1: Retrieve (retrieve.py)

```python
def retrieve(concept: RawConcept, top_k: int, embedder: Embedder) -> list[CandidateKU]:
```

1. Embed the concept label (only the label text)
2. Query pgvector for top-k nearest `knowledge_unit` vectors by cosine distance
3. Return `list[CandidateKU(ku_id, label, similarity_score)]`

Similarity score is carried through all stages for inspection but never used as the sole decision signal.

---

### 6. Alignment Pipeline — Stage 2: Rerank (rerank.py)

```python
def rerank(
    concept: RawConcept,
    candidates: list[CandidateKU],
    course: Course,
    co_concepts: list[RawConcept],   # other concepts from same course
    all_courses: dict[str, Course],  # for level lookup
) -> list[RankedCandidateKU]:
```

Reranking score formula:

```text
rerank_score = w1 * similarity
             + w2 * co_occurrence_signal
             + w3 * level_proximity
             + w4 * department_prior
```

Where:

- `co_occurrence_signal`: fraction of `co_concepts` whose current best candidate shares the same knowledge area as this candidate (strongest signal — carries information the embedding does not)
- `level_proximity`: `1 - |normalised_course_level - ku_depth_proxy|` where course level is normalised from 100–600 range to [0,1] and `ku_depth_proxy` is estimated from tier (core=0.3, elective=0.7)
- `department_prior`: a soft fractional boost (weight w4 = 0.05) if the candidate's knowledge area matches a known CS-adjacent area. Never zero-out any candidate — not a hard filter
- Default weights: w1=0.4, w2=0.35, w3=0.2, w4=0.05 (configurable)

Output: candidates sorted by `rerank_score` descending.

---

### 7. Alignment Pipeline — Stage 3: Reject (reject.py)

```python
def reject(
    concept: RawConcept,
    candidates: list[RankedCandidateKU],
    graph: ConceptGraphSnapshot,
) -> list[RankedCandidateKU]:   # surviving candidates
```

For each candidate KU, checks:

1. **Cycle check**: would adding `concept → ku` create a cycle in the current concept dependency subgraph? Uses DFS on the in-memory graph snapshot.
2. **Ordering violation**: would this alignment imply a concept in a lower-level course depends on a concept in a higher-level course, contradicting a declared prerequisite?

Rejected candidates are logged with reason. If all candidates are rejected, the concept is marked `unaligned`.

The graph snapshot is a read-only view of concepts already aligned in this run, updated after each concept is committed.

---

### 8. Alignment Pipeline — Stage 4: Verify (verify.py)

```python
def verify(
    concept: RawConcept,
    candidates: list[RankedCandidateKU],
    config: ExtractionConfig,
) -> AlignmentResult:
```

Selects the top-ranked surviving candidate. Confidence is the winner's
temperature-scaled softmax probability against its strongest rival (the top
two rerank scores) — a margin of separation from the closest competitor:

```text
confidence = 1 / (1 + exp((score_runner_up - score_winner) / T))
```

`T` is `confidence_temperature` (default 0.10). This ranges in [0.5, 1.0]:
a clear winner (large gap to the runner-up) approaches 1.0, while a near-tie
approaches 0.5. Using the top two rather than the whole field avoids diluting
the winner across many similar candidates — with `top_k = 10`, a softmax over
all candidates crushes even a clear winner toward `1/k`.

This replaced an earlier share-of-top-two ratio
(`winner / (winner + runner_up)`), which was structurally pinned near 0.5 and
did not reflect alignment quality.

(If only one candidate survives, confidence = `rerank_score_of_winner`
normalised to [0,1] by sigmoid.)

If confidence < `min_confidence` (default 0.3): `LOW_CONFIDENCE_UNALIGNED`.
Otherwise: `ALIGNED` with `knowledge_unit_id` and `confidence`.

---

### 9. Aligner

Runs all four stages in sequence per concept. Produces a `Concept` record conforming to the canonical schema.

```python
def align(raw: RawConcept, course: Course, co_concepts: list[RawConcept], ...) -> Concept:
```

Error handling: any unhandled exception in a stage is caught, logged as an alignment failure for that concept, and the concept is marked `unaligned`. The pipeline never halts on a single concept failure.

---

### 10. CoverageIndex

A lightweight in-memory and Neo4j-backed index of knowledge unit → courses:

```python
class CoverageIndex:
    def courses_for_ku(self, ku_id: str) -> list[str]: ...
    def thin_coverage_units(self, min_courses: int = 1) -> list[str]: ...
```

Built from the aligned `Concept` records at the end of each extraction run. Persisted in Neo4j as `KnowledgeUnit` node properties. Used by the advisory query layer.

---

### 11. ExtractionRunner

Orchestrates the full per-course loop:

```text
load vocabulary (cs2023_vocabulary.json)
embed all KU labels → pgvector (idempotent: skip if already embedded)
for each Course:
  → ConceptExtractor.extract(course.description) → list[RawConcept]
  → for each RawConcept:
      → Aligner.align() → Concept
      → write Concept to Neo4j
      → store concept embedding in pgvector
→ CoverageIndex.build()
→ ExtractionSummary.write()
```

Idempotent: if a `Concept` for `(course_id, label)` already exists in Neo4j, it is skipped unless `--force` is passed.

---

### 12. Neo4j schema

Nodes: `(:Course {course_id})`, `(:Concept {concept_id, label, confidence, model_id, alignment_status})`, `(:KnowledgeUnit {ku_id, label, knowledge_area, tier})`

Relationships:

- `(:Concept)-[:EXTRACTED_FROM]->(:Course)` — declared, from ingestion
- `(:Concept)-[:ALIGNED_TO {confidence, model_id}]->(:KnowledgeUnit)` — inferred

All Cypher queries use openCypher syntax only. No APOC procedures, no GDS, no Neo4j-specific extensions are used, so the schema is portable to any openCypher-compatible graph store.

---

## Data flow diagram

```text
CS2023 PDF ──► CS2023PdfParser ──► SeedWriter ──► data/cs2023_vocabulary.json
                                                           │
                                                           ▼
Course[] ──► ConceptExtractor ──► RawConcept[]         Embedder
                 (LLM)                │            (KU embeddings)
                                      ▼                   │
                               Stage 1: Retrieve ◄────────┘
                                      │
                               Stage 2: Rerank
                                      │
                               Stage 3: Reject
                                      │
                               Stage 4: Verify
                                      │
                               Concept records
                                      │
                            ┌─────────┴──────────┐
                            ▼                    ▼
                          Neo4j              pgvector
                     (Concept nodes)    (concept embeddings)
                            │
                      CoverageIndex
```

---

## CLI

```text
granular-extract [OPTIONS] COMMAND

Commands:
  bootstrap   Run CS2023 PDF bootstrap (one-time)
  run         Run concept extraction + alignment on ingested courses
  coverage    Print coverage report for current graph

Options (run):
  --config PATH
  --force           Re-extract all courses (skip idempotency check)
  --courses LIST    Comma-separated course IDs (subset run)
  --dry-run         Extract concepts but do not write to Neo4j
```

---

## Dependencies

- `pdfplumber` — PDF text extraction
- `openai` (or compatible) — LLM + embedding API
- `psycopg2` + `pgvector` Python extension — vector store
- `neo4j` Python driver (openCypher queries only — no APOC/GDS; swappable to any openCypher-compatible driver)
- `granular.schema` — canonical schema types

## openCypher portability note

All Cypher in this package uses openCypher syntax only. No APOC, GDS, or Neo4j-specific procedures are called. The graph store is abstracted behind `GraphClient` (from `granular.inference`) so the underlying store can be swapped by changing the driver and connection config.
