# Design — catalogue-ingestion

## Overview

The ingestion pipeline is a Python package (`granular.ingestion`) with two source adapters — an HTML scraper for `catalog.purdue.edu` (Modern Campus Acalog) and an OData client for `api.purdue.io` — feeding a shared normaliser that produces canonical schema records. The pipeline is a CLI tool (`granular-ingest`) with no server process.

All network I/O is isolated in adapter classes. The normaliser is pure Python with no network calls. This boundary makes the normaliser unit-testable without hitting the network.

---

## Package layout

```text
src/
  granular/
    ingestion/
      __init__.py
      cli.py                  # granular-ingest entry point
      config.py               # IngestConfig dataclass (from env / config file)
      robots.py               # RobotsCache — fetch, parse, check
      http_client.py          # RateLimitedClient wrapping httpx
      adapters/
        __init__.py
        acalog/
          __init__.py
          catalogue.py        # AcalogCatalogueAdapter — programme + course page discovery
          course_parser.py    # parse one course HTML page → RawCourse
          programme_parser.py # parse one programme HTML page → RawProgramme
          prereq_parser.py    # parse prerequisite strings → PrerequisiteRule
        purdue_io/
          __init__.py
          client.py           # PurdueIoClient — OData queries
          mapper.py           # OData record → RawCourse fields
      normaliser.py           # RawCourse / RawProgramme → canonical schema records
      runner.py               # IngestRunner — orchestrates adapters + normaliser
      summary.py              # IngestSummary dataclass + JSON writer
data/
  ingestion/
    output/                   # written by runner; .gitignored except summaries
```

---

## Component breakdown

### 1. IngestConfig

Loaded from a TOML config file and/or environment variables. Fields:

```python
@dataclass
class IngestConfig:
    catalogue_base_url: str        # default: "https://catalog.purdue.edu"
    purdue_io_base_url: str        # default: "https://api.purdue.io/odata"
    subject_filter: str            # default: "CS"
    requests_per_second: float     # default: 1.0
    output_dir: Path
    summary_path: Path
    failure_threshold_pct: float   # default: 10.0
    force_refetch: bool            # default: False
    since_date: Optional[date]     # --since flag
    user_agent: str                # default: "GranularResearchBot/1.0"
    adapter_name: str              # default: "purdue_acalog"
    adapter_version: str           # semver
```

---

### 2. RobotsCache

Fetches `{base_url}/robots.txt` once at startup, parses it with Python's `urllib.robotparser.RobotFileParser`, and exposes `is_allowed(url: str) -> bool`. Results are cached for the run duration. Any URL returning `False` is logged as `robots_disallowed` and skipped; no exception is raised.

---

### 3. RateLimitedClient

Wraps `httpx.Client` (sync). Enforces `requests_per_second` via a token bucket. Handles:

- HTTP 429 + `Retry-After`: sleeps for the stated duration then retries once
- Non-200 responses on course pages: returns a `FetchFailure` rather than raising
- Timeouts (configurable, default 30s): returns a `FetchFailure`

Conditional GET support: stores `ETag` / `Last-Modified` per URL in a local SQLite cache (`fetch_cache.db`). On re-runs without `--force`, sends `If-None-Match` / `If-Modified-Since`; a 304 response reuses the cached body.

---

### 4. AcalogCatalogueAdapter

Discovers all CS course and programme URLs by walking the Acalog catalogue index pages. Modern Campus Acalog exposes a predictable URL structure:

- Course list: `catalog.purdue.edu/content.php?catoid={N}&filter[3]=CS&filter[item_type]=3`
- Course detail: `catalog.purdue.edu/preview_course_nopop.php?catoid={N}&coid={M}`
- Programme list: `catalog.purdue.edu/content.php?catoid={N}&filter[item_type]=1`

The adapter:

1. Fetches the course list pages (paginated) to collect all `(catoid, coid)` pairs for CS courses
2. Fetches each course detail page → `CourseParser`
3. Fetches CS programme pages → `ProgrammeParser`

The current catalogue year's `catoid` is discovered from the catalogue index page rather than hard-coded, so the adapter survives a catalogue year rollover without a code change.

---

### 5. CourseParser

Parses one Acalog course detail HTML page using `BeautifulSoup4`. Produces a `RawCourse` intermediate:

```python
@dataclass
class RawCourse:
    subject_code:    str
    course_number:   str
    title:           str
    description:     str
    credits_raw:     str          # verbatim, e.g. "3.00" or "1.00 to 3.00"
    prereqs_raw:     str          # verbatim prerequisite block
    cross_list_raw:  list[str]    # verbatim cross-listing strings
    level_raw:       str          # "Undergraduate" / "Graduate" from page
    source_url:      str
    retrieved_at:    datetime
    source_revision: Optional[str]
```

Credit parsing: regex handles fixed (`3.00`), range (`1.00 to 3.00`), and variable (`Variable`) credit formats. Variable credits produce a `CreditRange(0, 0)` with a logged warning.

---

### 6. ProgrammeParser

Parses one programme HTML page. Extracts programme name, level, and all requirement blocks. Each block is parsed into a `RawRequirementRule`:

```python
@dataclass
class RawRequirementRule:
    verbatim_text: str
    rule_type_hint: Optional[str]   # "hours", "courses", "gpa" if detectable
    course_refs:    list[str]        # course numbers mentioned in the block
```

Programme pages are less structurally consistent than course pages. The parser uses a best-effort approach: extracts what it can, marks the rest `not_machine_checkable`. This is intentional (research artefact).

---

### 7. PrereqParser

Converts a verbatim prerequisite string into a `PrerequisiteRule`. Uses a hand-written recursive descent parser covering:

- Single course: `CS 18000`
- AND-list: `CS 18000 and CS 18200`
- OR-list: `CS 18000 or CS 18200`
- With grade: `CS 18000 (C or better)`
- Nested: `(CS 18000 or CS 18200) and CS 25100`

Anything not matching these patterns → `machine_checkable: False`, verbatim text retained.

The parser is deliberately narrow. It does not attempt to parse English prose conditions ("permission of instructor", "junior standing"). Those always produce `not_machine_checkable`.

---

### 8. PurdueIoClient

OData client using `httpx`. Queries:

```text
GET /odata/Courses?$filter=Subject eq 'CS'&$select=Number,Title,Description,CreditHours,CourseID
```

Returns a list of `ODataCourse` dicts. The mapper converts these to `RawCourse` fields for cross-checking only (not as primary source).

Fallback: if the OData endpoint returns non-200 or times out, `PurdueIoClient` raises `ODataUnavailable`. The runner catches this, logs the fallback, and continues with HTML-only data.

Conflict resolution: if `ODataCourse.Description` differs from the HTML-parsed description, the HTML value is used and the discrepancy is logged with both values.

---

### 9. Normaliser

Pure function: `normalise(raw: RawCourse, config: IngestConfig) -> Course`. No network, no I/O.

Steps:

1. Parse credits string → `float` or `CreditRange`
2. Parse level string → `ProgrammeLevel`
3. Run `PrereqParser` on `prereqs_raw` → `list[PrerequisiteRule]`
4. Produce `DeclaredEdge(PREREQUISITE)` for each structured prerequisite
5. Parse cross-listings → `list[str]` of course IDs; produce `DeclaredEdge(CROSS_LISTING)` for each
6. Construct `ProvenanceRecord` from config + raw fields
7. Construct and return `Course` (validated by schema `__post_init__`)

Any `SchemaValidationError` from step 7 is caught, logged as a normaliser failure for that course, and re-raised to the runner as a `NormaliserError`.

---

### 10. IngestRunner

Orchestrates the full pipeline:

```text
RobotsCache.load()
→ AcalogCatalogueAdapter.discover_course_urls()
→ [for each url] RateLimitedClient.get() → CourseParser.parse() → Normaliser.normalise()
→ PurdueIoClient.fetch_all() [optional, with fallback]
→ AcalogCatalogueAdapter.discover_programme_urls()
→ [for each url] ProgrammeParser.parse() → normalise_programme()
→ write output records
→ IngestSummary.write()
→ exit code check (failure threshold)
```

Concurrency: sequential by default. An optional `--workers N` flag enables `concurrent.futures.ThreadPoolExecutor` for page fetches, respecting the rate limiter across threads via a shared token bucket lock.

---

### 11. IngestSummary

```python
@dataclass
class IngestSummary:
    run_id:                   str      # UUID
    started_at:               datetime
    completed_at:             datetime
    courses_attempted:        int
    courses_succeeded:        int
    courses_failed:           list[FailureRecord]
    courses_skipped:          list[SkipRecord]
    programmes_ingested:      int
    prereqs_structured:       int
    prereqs_unstructured:     int
    odata_fallback_used:      bool
    odata_discrepancies:      int
    duration_seconds:         float
```

Written to `summary_path` as JSON. Exit code 1 if `courses_failed / courses_attempted > failure_threshold_pct / 100`.

---

## Data flow diagram

```text
catalog.purdue.edu ──► RobotsCache ──► AcalogCatalogueAdapter
                                              │
                              ┌───────────────┤
                              ▼               ▼
                        CourseParser   ProgrammeParser
                              │               │
                              ▼               ▼
                     PurdueIoClient ──► Normaliser
                     (cross-check)          │
                                            ▼
                                    canonical schema records
                                            │
                                   ┌────────┴────────┐
                                   ▼                 ▼
                              Course[]           Programme[]
                              DeclaredEdge[]     RequirementRule[]
                                            │
                                            ▼
                                      IngestSummary
```

---

## CLI

```text
granular-ingest [OPTIONS]

Options:
  --config PATH       TOML config file (default: ingest.toml)
  --since DATE        ISO-8601 date; skip pages not modified since
  --force             Re-fetch all pages regardless of cache
  --workers N         Parallel fetch workers (default: 1)
  --output-dir PATH   Output directory for records
  --dry-run           Discover URLs and report counts; do not fetch or write
```

---

## Dependencies

- `httpx` — async-capable HTTP client
- `beautifulsoup4` + `lxml` — HTML parsing
- `urllib.robotparser` (stdlib) — robots.txt
- `granular.schema` — canonical schema types
- `toml` / `tomllib` (stdlib ≥ 3.11) — config parsing
- SQLite (stdlib) — fetch cache
