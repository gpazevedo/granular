# Design — advisory-queries

## Overview

The advisory layer has two components:

1. **Backend** (`granular.api`) — a Python FastAPI application exposing a REST API. Queries Neo4j and pgvector. Stateless: no session, no user store.
2. **Frontend** (`apps/web`) — a Next.js 14 (App Router) TypeScript application. Calls the backend API. Renders results for students.

The primary capability is interest-driven discovery: plain-English query → CS2023 knowledge unit resolution → ranked course list + course combinations. Secondary advisory queries (credit consequence, overlap, readiness, unlock, programme fit) are additional endpoints on the same backend.

---

## Repository layout additions

```text
src/
  granular/
    api/
      __init__.py
      main.py               # FastAPI app, CORS, lifespan
      config.py             # APIConfig
      dependencies.py       # FastAPI dependency injection (db clients)
      routers/
        discover.py         # POST /api/v1/discover
        credit.py           # GET  /api/v1/courses/{id}/credit-consequence
        overlap.py          # POST /api/v1/courses/{id}/overlap
        readiness.py        # POST /api/v1/courses/{id}/readiness
        unlock.py           # GET  /api/v1/courses/{id}/unlock
        fit.py              # POST /api/v1/programmes/{id}/fit
      services/
        resolver.py         # QueryResolver — plain-English → KU ids
        matcher.py          # CourseMatcher — KU ids → ranked courses
        combinator.py       # CombinationBuilder — ranked courses → combinations
        graph_queries.py    # Neo4jQueryService — all Cypher queries
        vector_queries.py   # VectorQueryService — pgvector queries
      models/
        requests.py         # Pydantic request models
        responses.py        # Pydantic response models
      guards/
        language_guard.py   # EntitlementLanguageGuard
apps/
  web/
    app/
      page.tsx              # home / discover page
      layout.tsx
      components/
        SearchBar.tsx
        LevelFilter.tsx
        CourseCard.tsx
        CombinationCard.tsx
        MetricBadge.tsx
        CoverageBar.tsx
        CaveatBanner.tsx
        ThinCoverageAlert.tsx
        NoResultsMessage.tsx
    lib/
      api.ts                # typed API client
      types.ts              # TypeScript types matching response models
    styles/
      globals.css
```

---

## Backend component breakdown

### 1. APIConfig

```python
@dataclass
class APIConfig:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    pgvector_dsn: str
    embedding_model_id: str
    frontend_origin: str          # CORS allowed origin
    min_coverage_courses: int     # thin-coverage threshold, default: 1
    max_combinations: int         # default: 5
    max_combination_size: int     # default: 3
    entitlement_patterns: list[str]  # regex patterns for language guard
```

---

### 2. QueryResolver

Resolves a plain-English query to a list of CS2023 `KnowledgeUnit` ids.

```python
class QueryResolver:
    def resolve(self, query: str) -> ResolutionResult: ...
```

Steps:

1. Embed the query text (bare text only — no metadata appended)
2. Query pgvector for top-k `knowledge_unit` embeddings by cosine similarity (k=15)
3. Apply the same reranking weights as the extraction pipeline (co-occurrence not available at query time — uses similarity + soft domain prior only)
4. Filter candidates with reranked score < 0.3
5. Return `ResolutionResult(ku_ids: list[str], model_id: str, resolved: bool)`

If `ku_ids` is empty: `resolved=False` → router returns `no_concepts_resolved` response.

The resolver never matches against course description text directly. All matching goes through the vocabulary.

---

### 3. CourseMatcher

```python
class CourseMatcher:
    def match(
        self,
        ku_ids: list[str],
        level_filter: LevelFilter,
    ) -> list[CourseMatchResult]: ...
```

Cypher query pattern (openCypher — no Neo4j-specific extensions):

```cypher
MATCH (c:Course)-[:EXTRACTED_FROM]<-[:EXTRACTED_FROM]-(concept:Concept)
      -[:ALIGNED_TO]->(ku:KnowledgeUnit)
WHERE ku.ku_id IN $ku_ids
  AND ($level = 'all' OR c.level = $level)
WITH c,
     collect(DISTINCT ku.ku_id) AS covered_kus,
     avg(concept.confidence) AS mean_confidence
RETURN c, covered_kus, mean_confidence
ORDER BY mean_confidence DESC, size(covered_kus) DESC
```

Produces `list[CourseMatchResult]`:

```python
@dataclass
class CourseMatchResult:
    course_id:        str
    course_number:    str
    subject_code:     str
    title:            str
    level:            str
    credits:          str
    description_excerpt: str    # first 200 chars of description
    relevance_score:  float     # mean alignment confidence of matched concepts
    covered_ku_ids:   list[str]
    coverage_breadth: str       # "N of M concepts"
    evidence_basis:   str       # always "inferred"
    confidence:       float
    caveat:           str
```

`caveat` is a fixed string: `"Coverage is inferred from course descriptions and may not reflect actual course content."` — never varies, never uses entitlement language.

---

### 4. CombinationBuilder

```python
class CombinationBuilder:
    def build(
        self,
        courses: list[CourseMatchResult],
        all_ku_ids: list[str],
        declared_prereqs: list[DeclaredEdge],
        config: APIConfig,
    ) -> list[CombinationResult]: ...
```

Algorithm:

1. Take the top-N individual results (N = min(20, len(courses)) to bound the search)
2. Generate all combinations of size 2 and 3 from those N courses using `itertools.combinations`
3. For each combination:
   - Compute `union_kus = set.union(*[set(c.covered_ku_ids) for c in combo])`
   - Skip if `len(union_kus) <= max(c.covered_ku_ids for c in combo)` — no improvement over best single course
   - Compute `redundancy`: for each pair within the combo, find `set(a.covered_ku_ids) & set(b.covered_ku_ids)`
   - Look up declared prerequisite relationships between courses in the combo from `declared_prereqs`
   - Compute `combined_relevance = mean(c.relevance_score for c in combo)`
4. Sort by `len(union_kus)` descending, then `combined_relevance` descending
5. Return top `max_combinations` (default 5)

```python
@dataclass
class CombinationResult:
    courses:              list[CourseMatchResult]
    combined_coverage_breadth: str    # "N of M concepts"
    combined_ku_ids:      list[str]   # deduplicated union
    redundancies:         list[RedundancyNote]
    prerequisite_order:   list[PrereqNote]
    combined_relevance:   float
    evidence_basis:       str         # always "inferred"
    caveat:               str

@dataclass
class RedundancyNote:
    course_a_number: str
    course_b_number: str
    overlapping_ku_labels: list[str]

@dataclass
class PrereqNote:
    take_first: str    # course number
    then:        str   # course number
    declared:    bool  # True if from declared edge; False = "no ordering published"
```

If no declared prerequisite exists between any pair in a combination, `prerequisite_order` contains one `PrereqNote` with `declared=False` and a message: `"No ordering constraint is published between these courses."`

---

### 5. Neo4jQueryService

All Cypher is centralised here. Exposes typed methods:

```python
class Neo4jQueryService:
    def get_programme_membership(self, course_id: str) -> list[ProgrammeMembership]: ...
    def get_declared_prerequisites(self, course_id: str) -> list[PrereqResult]: ...
    def get_forward_unlock(self, course_id: str) -> list[CourseRef]: ...
    def get_overlap(self, target_course_id: str, completed_ids: list[str]) -> OverlapResult: ...
    def get_programme_fit(self, programme_id: str, completed_ids: list[str]) -> FitResult: ...
    def get_thin_coverage_units(self, ku_ids: list[str]) -> list[str]: ...
    def get_declared_prereqs_between(self, course_ids: list[str]) -> list[DeclaredEdge]: ...
```

No Cypher is written in routers or services outside this class.

---

### 6. EntitlementLanguageGuard

A pure function applied to all response text fields before the response is serialised:

```python
def check(text: str, patterns: list[str]) -> GuardResult:
    # Returns GuardResult(clean=True) or GuardResult(clean=False, matched_pattern=str)
```

Default forbidden patterns (regex):

- `\bexempt\b`, `\bskip\b` (in context of a course), `\byou (will|can|should) master\b`
- `\bcovers everything\b`, `\ball you need\b`, `\bfully prepares\b`

If a match is found, the backend raises a 500 `EntitlementLanguageError` and logs the offending text. This is a hard failure — it surfaces immediately during development rather than silently shipping bad language. The patterns list is configurable in `APIConfig`.

---

### 7. Routers

#### POST /api/v1/discover

```python
class DiscoverRequest(BaseModel):
    query: str
    level: Literal["undergraduate", "graduate", "all"] = "all"

class DiscoverResponse(BaseModel):
    resolved_kus:     list[KULabel]
    courses:          list[CourseMatchResult]
    combinations:     list[CombinationResult]
    thin_coverage:    list[ThinCoverageNote]   # empty list if none
    status:           Literal["ok", "no_concepts_resolved", "no_courses_found"]
    status_message:   Optional[str]
```

Flow:

1. `QueryResolver.resolve(request.query)`
2. If not resolved → return `status="no_concepts_resolved"`
3. `CourseMatcher.match(ku_ids, level_filter)`
4. If empty → return `status="no_courses_found"` with resolved KUs
5. Check thin coverage via `Neo4jQueryService.get_thin_coverage_units(ku_ids)`
6. `CombinationBuilder.build(courses, ku_ids, prereqs)`
7. Apply `EntitlementLanguageGuard` to all text fields
8. Return `status="ok"`

#### Secondary routers

Each secondary router follows the same pattern: typed request model, typed response model, single service call, `EntitlementLanguageGuard` applied before return, `evidence_basis` always set.

---

## Frontend component breakdown

### Page: `/` (Discover)

Layout:

```
┌─────────────────────────────────────────┐
│  [SearchBar — plain-English input]      │
│  [LevelFilter — UG / Grad / All]        │
├─────────────────────────────────────────┤
│  [ThinCoverageAlert — if applicable]    │
├──────────────┬──────────────────────────┤
│ Individual   │  Course Combinations     │
│ Results      │                          │
│ [CourseCard] │  [CombinationCard]       │
│ [CourseCard] │  [CombinationCard]       │
│   ...        │    ...                   │
└──────────────┴──────────────────────────┘
```

On `no_concepts_resolved` or `no_courses_found`: full-width `<NoResultsMessage>` with the status message from the API. No empty list.

### CourseCard

Displays: course number + title, level badge, credit hours, `<MetricBadge relevance={score}>`, `<CoverageBar covered={N} total={M}>`, evidence basis label (`inferred`), `<CaveatBanner>`.

### CombinationCard

Displays: ordered list of course pills (with prerequisite arrow icons where `declared=true`), combined coverage bar, redundancy warnings per overlapping pair (collapsible), `<CaveatBanner>`.

### CaveatBanner

A small, always-visible banner: `"Coverage is inferred from course descriptions and may not reflect actual course content."` Styled as a muted note, not an error. Never hidden.

### NoResultsMessage

Renders the API's `status_message` verbatim, plus the list of resolved knowledge units (if any) and a suggestion to rephrase. Never an empty state.

### Entitlement language check (frontend)

A `useEffect` in each result component scans rendered text for the same forbidden patterns as the backend guard. If a match is found in development, it throws a React error boundary — surfacing backend bypasses immediately. In production, it logs to console and suppresses the offending field.

---

## API client (`lib/api.ts`)

```typescript
export async function discover(
  query: string,
  level: "undergraduate" | "graduate" | "all"
): Promise<DiscoverResponse> { ... }
```

All request/response types in `lib/types.ts` mirror the Pydantic models exactly. Generated from the OpenAPI spec exported by FastAPI (`/openapi.json`).

---

## Data flow diagram

```text
Student (browser)
    │  query + level
    ▼
Next.js frontend (apps/web)
    │  POST /api/v1/discover
    ▼
FastAPI backend (granular.api)
    │
    ├──► QueryResolver ──► pgvector (KU embeddings)
    │         │
    │         ▼ ku_ids
    ├──► CourseMatcher ──► Neo4j (Concept + Course + KU nodes)
    │         │
    │         ▼ courses
    ├──► CombinationBuilder ──► Neo4j (declared prereqs)
    │         │
    │         ▼ combinations
    ├──► EntitlementLanguageGuard
    │
    └──► DiscoverResponse
              │
              ▼
        Next.js renders CourseCards + CombinationCards
```

---

## Development setup

```text
# Backend
uvicorn granular.api.main:app --reload --port 8000

# Frontend
cd apps/web && npm run dev    # Next.js on port 3000

# CORS: backend allows http://localhost:3000 in development
```

---

## Dependencies

**Backend:**

- `fastapi` + `uvicorn`
- `pydantic` v2
- `neo4j` Python driver (openCypher queries only — no APOC/GDS; swappable to any openCypher-compatible driver)
- `psycopg2` + `pgvector`
- `openai` (or compatible) — embedding API for QueryResolver
- `granular.schema`

**Frontend:**

- `next` 14 (App Router)
- `typescript`
- `tailwindcss` — styling
- `swr` — data fetching / revalidation
