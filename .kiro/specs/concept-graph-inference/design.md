# Design — concept-graph-inference

## Overview

The inference pipeline is a Python package (`granular.inference`) that operates on the aligned `Concept` nodes and `KnowledgeUnit` nodes already in Neo4j, and infers two types of edges: `concept_dependency` (directed, A requires B) and `concept_similarity` (undirected, A and B are the same idea in different courses). All outputs are `InferredEdge` records written to Neo4j. The pipeline is a CLI tool (`granular-infer`).

The pipeline never calls a model for edge decisions. Inference is structural: it uses the shape of the curriculum (course levels, declared prerequisite edges, co-occurrence of knowledge units) to decide whether a dependency exists. Embedding similarity informs candidate generation only — it never decides an edge.

---

## Package layout

```text
src/
  granular/
    inference/
      __init__.py
      cli.py                      # granular-infer entry point
      config.py                   # InferenceConfig
      graph.py                    # GraphClient — Neo4j read/write wrapper
      snapshot.py                 # ConceptGraphSnapshot — in-memory DAG for cycle checks
      signals/
        __init__.py
        course_level.py           # CourseLevelSignal
        prerequisite_prior.py     # PrerequisitePriorSignal
        ku_cooccurrence.py        # KUCooccurrenceSignal
      scorer.py                   # DependencyScorer — combines signals → candidate score
      cycle.py                    # CycleResolver — DAG guarantee
      ordering.py                 # OrderingValidator — declared prerequisite consistency
      dependency.py               # DependencyInferrer — produces concept_dependency edges
      similarity.py               # SimilarityInferrer — produces concept_similarity edges
      runner.py                   # InferenceRunner — orchestrates full pipeline
      summary.py                  # InferenceSummary dataclass + JSON writer
```

---

## Component breakdown

### 1. InferenceConfig

```python
@dataclass
class InferenceConfig:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    confidence_high: float          # default: 0.7
    confidence_medium_low: float    # default: 0.4
    min_dependency_score: float     # default: 0.35
    rejection_threshold_pct: float  # default: 20.0 — exit non-zero if exceeded
    model_id: str                   # identifier recorded on all InferredEdges; no model is called — this records the pipeline version
    adapter_name: str
    adapter_version: str
    output_dir: Path
    summary_path: Path
    signal_weights: SignalWeights

@dataclass
class SignalWeights:
    course_level:       float = 0.45
    prerequisite_prior: float = 0.40
    ku_cooccurrence:    float = 0.15
```

`model_id` here records the pipeline version string (e.g. `granular-inference/1.0.0`), not an LLM — it satisfies the canonical schema invariant that inferred facts carry a model identifier.

---

### 2. GraphClient

Thin wrapper around the `neo4j` Python driver. Exposes typed query methods:

```python
class GraphClient:
    def get_all_concepts(self) -> list[ConceptNode]: ...
    def get_courses_for_concept(self, concept_id: str) -> list[CourseNode]: ...
    def get_declared_prerequisites(self) -> list[DeclaredEdgeRecord]: ...
    def get_concepts_by_ku(self, ku_id: str) -> list[ConceptNode]: ...
    def write_inferred_edge(self, edge: InferredEdge) -> None: ...
    def write_rejected_edge(self, edge: RejectedEdge) -> None: ...
    def concept_exists(self, concept_id: str) -> bool: ...
```

All writes are idempotent: `MERGE` on `edge_id` rather than `CREATE`.

---

### 3. ConceptGraphSnapshot

An in-memory directed graph (using Python's `dict[str, set[str]]` adjacency list) built from the `concept_dependency` edges committed so far in the current run. Used exclusively for cycle detection — not a full graph replica.

```python
class ConceptGraphSnapshot:
    def add_edge(self, from_id: str, to_id: str) -> None: ...
    def has_cycle(self) -> bool: ...          # DFS
    def find_cycle_edges(self) -> list[tuple[str, str]]: ...
```

Rebuilt from Neo4j at the start of each run (loading existing inferred dependency edges), then updated in memory as new edges are committed.

---

### 4. Signals

Three independent signals contribute to the dependency score for a concept pair (A, B) where A is the candidate dependent and B is the candidate dependency:

#### CourseLevelSignal

```python
def score(concept_a: ConceptNode, concept_b: ConceptNode,
          courses: dict[str, CourseNode]) -> float:
```

Normalises course numbers to [0, 1] within the 100–600 range. Returns a score proportional to how much higher concept A's course level is than concept B's course level. A pair where A is in a 400-level course and B is in a 200-level course scores higher than a pair at adjacent levels. Pairs at the same level or reversed score 0.

#### PrerequisitePriorSignal

```python
def score(concept_a: ConceptNode, concept_b: ConceptNode,
          declared_prereqs: set[tuple[str, str]]) -> float:
```

Returns 1.0 if the course containing A has a declared prerequisite relationship (direct or transitive, up to depth 3) on the course containing B. Returns 0.5 for transitive depth 1, 0.3 for depth 2–3. Returns 0.0 otherwise. This is the strongest signal when available.

#### KUCooccurrenceSignal

```python
def score(concept_a: ConceptNode, concept_b: ConceptNode,
          ku_graph: dict[str, list[str]]) -> float:
```

Checks whether the knowledge units of A and B co-occur in the same knowledge area and whether other concept pairs from the same course pair have already been inferred as dependencies (bootstrapping signal). Returns a fractional score in [0, 1].

---

### 5. DependencyScorer

Combines the three signal scores into a single candidate score:

```python
def score(a: ConceptNode, b: ConceptNode, context: ScoringContext) -> float:
    return (
        w.course_level       * CourseLevelSignal.score(a, b, context.courses)
      + w.prerequisite_prior * PrerequisitePriorSignal.score(a, b, context.prereqs)
      + w.ku_cooccurrence    * KUCooccurrenceSignal.score(a, b, context.ku_graph)
    )
```

A pair with score < `min_dependency_score` (default 0.35) is not proposed as a candidate edge.

---

### 6. DependencyInferrer

Main inference loop for `concept_dependency` edges:

```text
for each concept A (aligned):
    for each concept B where:
        - B is in a different course than A
        - B's course level ≤ A's course level  (hard filter — never infer upward)
        - (A.ku_id, B.ku_id) are in the same or adjacent knowledge areas
    → score(A, B)
    → if score ≥ min_dependency_score: propose edge (A depends-on B)

for each proposed edge:
    → OrderingValidator.check(A, B)   [reject if contradicts declared prereq direction]
    → if passes: add to candidate set

CycleResolver.resolve(candidate_set)   [remove lowest-confidence edges until DAG]

for each surviving edge:
    → construct InferredEdge(CONCEPT_DEPENDENCY, confidence=score, model_id=config.model_id)
    → GraphClient.write_inferred_edge(edge)
    → ConceptGraphSnapshot.add_edge(A.concept_id, B.concept_id)
```

The inner loop is `O(C²)` in the number of concepts. For Purdue CS (estimated 800–2000 concepts), this is tractable. If the corpus grows, the knowledge-area adjacency filter reduces the effective search space substantially.

---

### 7. SimilarityInferrer

Runs after dependency inference. Finds all pairs of aligned concepts that share the same `knowledge_unit_id` but come from different courses:

```cypher
MATCH (a:Concept)-[:ALIGNED_TO]->(ku:KnowledgeUnit)<-[:ALIGNED_TO]-(b:Concept)
WHERE a.source_course_id <> b.source_course_id AND id(a) < id(b)
RETURN a, b, ku, a.confidence AS conf_a, b.confidence AS conf_b
```

For each pair:

- `confidence = min(conf_a, conf_b)`
- If both confidences < 0.5: flag as `low_confidence_similarity` (still written, separately marked)
- Construct `InferredEdge(CONCEPT_SIMILARITY, confidence=..., model_id=...)`
- Write to Neo4j

No cycle check needed — similarity edges are undirected and not used in traversal queries.

---

### 8. CycleResolver

```python
def resolve(
    snapshot: ConceptGraphSnapshot,
    candidates: list[tuple[InferredEdge, float]]   # (edge, score)
) -> tuple[list[InferredEdge], list[RejectedEdge]]:
```

1. Add all candidate edges to a working copy of the snapshot
2. While `snapshot.has_cycle()`:
   a. Find a cycle via DFS
   b. Remove the candidate edge in the cycle with the lowest score
   c. Record it as `RejectedEdge(reason="cycle_prevention")`
3. Return surviving edges and rejected edges

Never raises. Cycle resolution is logged and counted in the summary.

---

### 9. OrderingValidator

```python
def check(
    concept_a: ConceptNode,   # proposed dependent
    concept_b: ConceptNode,   # proposed dependency
    declared_prereqs: set[tuple[str, str]]   # (course_id, prereq_course_id)
) -> ValidationResult:
```

Checks: does a declared prerequisite exist where course_B requires course_A (i.e. the declared direction is opposite to the inferred direction)? If so: `ValidationResult.CONTRADICTION`.

Also checks: is the inferred direction consistent with all transitive declared prerequisites up to depth 3? Inconsistency at any depth → `CONTRADICTION`.

Returns `ValidationResult.OK` or `ValidationResult.CONTRADICTION`. Contradictions are logged and the edge is written to `rejected_inferred_edges` in Neo4j.

---

### 10. Neo4j schema additions

New relationship types added by this pipeline. All property keys follow openCypher conventions — no Neo4j-specific types or index hints are used:

```text
(:Concept)-[:DEPENDS_ON {
    confidence: float,
    model_id: string,
    edge_id: string,
    source_url: string,
    retrieved_at: datetime,
    adapter_name: string,
    adapter_version: string
}]->(:Concept)

(:Concept)-[:SIMILAR_TO {
    confidence: float,
    low_confidence: boolean,
    model_id: string,
    edge_id: string,
    ...provenance fields
}]-(:Concept)
```

Rejected edges are stored in a separate label:

```text
(:RejectedInferredEdge {
    from_id, to_id, score, rejection_reason, run_id, rejected_at
})
```

---

### 11. InferenceRunner

```text
GraphClient.load()
ConceptGraphSnapshot.build_from_neo4j()
DependencyInferrer.run()   → writes DEPENDS_ON edges
SimilarityInferrer.run()   → writes SIMILAR_TO edges
coverage_report = build_knowledge_area_coverage_report()
InferenceSummary.write()
exit_code_check(rejection_threshold)
```

Idempotent: skips edges whose `edge_id` already exists in Neo4j unless `--force`.

---

### 12. InferenceSummary

```python
@dataclass
class InferenceSummary:
    run_id:                       str
    started_at:                   datetime
    completed_at:                 datetime
    concepts_processed:           int
    dependency_edges_inferred:    int
    similarity_edges_inferred:    int
    edges_rejected_cycle:         int
    edges_rejected_ordering:      int
    edges_below_min_score:        int
    confidence_mean:              float
    confidence_median:            float
    confidence_p10:               float
    confidence_p90:               float
    knowledge_area_coverage:      list[KACoverageRow]
    duration_seconds:             float
```

---

## Data flow diagram

```text
Neo4j (Concept + KU nodes)
        │
        ▼
  GraphClient.load()
        │
        ├──► ConceptGraphSnapshot (in-memory DAG)
        │
        ├──► DependencyInferrer
        │       │  CourseLevelSignal
        │       │  PrerequisitePriorSignal
        │       │  KUCooccurrenceSignal
        │       │        └──► DependencyScorer
        │       │
        │       ├──► OrderingValidator  (reject contradictions)
        │       └──► CycleResolver     (guarantee DAG)
        │               │
        │               ▼
        │        DEPENDS_ON edges → Neo4j
        │
        └──► SimilarityInferrer
                │
                ▼
         SIMILAR_TO edges → Neo4j
```

---

## CLI

```text
granular-infer [OPTIONS]

Options:
  --config PATH
  --force           Re-infer all edges (skip idempotency check)
  --dry-run         Score edges and report counts; do not write to Neo4j
  --report          Print knowledge-area coverage report and exit
```

---

## Dependencies

- `neo4j` Python driver
- `granular.schema` — canonical schema types
- No LLM, no embedding model, no pgvector

## openCypher portability note

All Cypher in this package uses openCypher syntax only. No APOC, GDS, or Neo4j-specific procedures are called. The `GraphClient` abstracts the driver so the underlying store can be swapped to any openCypher-compatible database (Amazon Neptune, Memgraph, etc.) by changing the driver and connection config.
