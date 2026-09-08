# Requirements — catalogue-ingestion

## Context

This spec defines the Purdue University adapter for the Modern Campus Acalog platform. The adapter parses the public catalogue at `catalog.purdue.edu` and the purdue.io OData v4 API, and produces records conforming to the canonical schema (`canonical-schema` spec).

The adapter does exactly one thing: parse declared facts into canonical schema objects. It makes no model calls, performs no inference, and introduces no derived relationships. It is a research artefact: it fails loudly on unexpected input rather than degrading silently.

**Sources:**

- Primary: `catalog.purdue.edu` — Modern Campus Acalog HTML pages (public, robots-permitting)
- Secondary: `api.purdue.io/odata/` — community OData v4 API (public, no authentication)

**Scope:** Computer Science courses and programmes, both undergraduate and graduate.

---

## Requirements

### REQ-CI-01 — robots.txt compliance

**User story:** As the operator of this system, I want the adapter to respect Purdue's crawling permissions, so that ingestion complies with the site's stated policies.

**Acceptance criteria:**

- BEFORE making any request to `catalog.purdue.edu`, THE SYSTEM SHALL fetch and parse `catalog.purdue.edu/robots.txt` and cache it for the duration of the ingestion run.
- THE SYSTEM SHALL NOT fetch any URL that is disallowed for the adapter's user-agent by `robots.txt`.
- IF a URL is disallowed, THE SYSTEM SHALL log it as a skipped record with reason `robots_disallowed` and continue; it SHALL NOT raise an unhandled exception.
- THE SYSTEM SHALL identify itself with a descriptive `User-Agent` header (e.g. `GranularResearchBot/1.0`).

---

### REQ-CI-02 — Course page ingestion

**User story:** As a downstream component, I want every CS course in the Purdue catalogue (UG and grad) to be available as a canonical `Course` record, so that concept extraction and advisory queries have complete input.

**Acceptance criteria:**

- THE SYSTEM SHALL ingest all courses whose subject code is `CS` from the current catalogue year on `catalog.purdue.edu`.
- FOR EACH course page, THE SYSTEM SHALL extract: course number, title, credit hours (or credit range), course description, declared prerequisites (verbatim and structured where possible), cross-listings, and whether the course is undergraduate or graduate level.
- THE SYSTEM SHALL produce one `Course` record per ingested course, conforming to the canonical schema.
- IF a course page is unreachable (HTTP error or timeout), THE SYSTEM SHALL record the failure with the course URL and HTTP status, skip that course, and continue ingestion; it SHALL NOT halt the run.
- THE SYSTEM SHALL record the source URL and retrieval timestamp on every `Course` record per REQ-CS-01.

---

### REQ-CI-03 — Programme ingestion

**User story:** As a downstream component, I want Purdue CS programmes (undergraduate and graduate) represented as canonical `Programme` records, so that advisory queries can answer programme-fit questions.

**Acceptance criteria:**

- THE SYSTEM SHALL ingest at minimum the following programmes: BS Computer Science (all tracks), MS Computer Science, PhD Computer Science.
- FOR EACH programme, THE SYSTEM SHALL extract: programme name, level (undergraduate/graduate), degree tracks where declared, and the list of requirement rules (credits required, required courses, elective course sets).
- THE SYSTEM SHALL produce one `Programme` record per programme, conforming to the canonical schema.
- WHEN a requirement rule resists structuring into a predicate, THE SYSTEM SHALL mark it `not_machine_checkable`, retain its verbatim text, and continue.
- THE SYSTEM SHALL record the source URL and retrieval timestamp on every `Programme` record.

---

### REQ-CI-04 — Prerequisite rule parsing

**User story:** As a downstream component, I want prerequisite rules structured as predicates where possible, so that readiness and unlock queries can operate over them.

**Acceptance criteria:**

- THE SYSTEM SHALL attempt to parse each verbatim prerequisite string into a structured `PrerequisiteRule` predicate covering at minimum: single-course prerequisites, AND-lists of courses, OR-lists of courses, and minimum-grade clauses.
- WHEN a prerequisite is successfully parsed, THE SYSTEM SHALL produce a `DeclaredEdge` of type `prerequisite` for each course reference in the rule.
- WHEN a prerequisite cannot be parsed, THE SYSTEM SHALL retain verbatim text, mark the rule `not_machine_checkable`, and NOT produce a `DeclaredEdge`.
- THE SYSTEM SHALL report the count of structured vs. unstructured prerequisites in the ingestion summary.

---

### REQ-CI-05 — purdue.io OData API as secondary source

**User story:** As a developer, I want the adapter to use the purdue.io structured API where it provides richer or more reliable data than HTML parsing, so that ingestion is more robust without depending on page layout.

**Acceptance criteria:**

- THE SYSTEM SHALL query `api.purdue.io/odata/Courses` filtered to subject `CS` and use the result to supplement or cross-check HTML-parsed records.
- IF the OData API returns a field that is also present on the HTML page and the values conflict, THE SYSTEM SHALL prefer the HTML page (the catalogue is authoritative) and log the discrepancy.
- IF the OData API is unavailable, THE SYSTEM SHALL fall back to HTML-only ingestion and log the fallback; it SHALL NOT halt the run.
- THE SYSTEM SHALL record `adapter_name: purdue_io_odata` and the API endpoint URL as provenance when a field value originates from the OData source.

---

### REQ-CI-06 — Cross-listing detection

**User story:** As a downstream component, I want cross-listed courses represented explicitly, so that the concept graph does not treat the same course as two independent entities.

**Acceptance criteria:**

- WHEN a course page declares a cross-listing (e.g. "Same as ECE 404"), THE SYSTEM SHALL record a `DeclaredEdge` of type `cross_listing` between the two course records.
- IF the cross-listed course is outside the CS subject scope, THE SYSTEM SHALL still record the edge and create a stub `Course` record for the external course with the fields available from the cross-listing reference; the stub SHALL carry `authority: derived`.

---

### REQ-CI-07 — Ingestion run summary and failure report

**User story:** As a developer running ingestion, I want a structured summary at the end of each run, so that I know what was ingested, what failed, and what was skipped without reading individual log lines.

**Acceptance criteria:**

- WHEN an ingestion run completes, THE SYSTEM SHALL produce a JSON summary containing: total courses attempted, courses successfully ingested, courses failed (with URLs and reasons), courses skipped (with reasons), programmes ingested, prerequisite rules structured, prerequisite rules marked `not_machine_checkable`, and total run duration.
- THE SYSTEM SHALL write the summary to a file at a configurable output path.
- THE SYSTEM SHALL exit with a non-zero code if the failure count exceeds a configurable threshold (default: 10% of attempted courses).

---

### REQ-CI-08 — Incremental re-ingestion

**User story:** As a developer, I want to re-run ingestion without re-fetching pages that have not changed, so that iteration is fast and source servers are not hammered.

**Acceptance criteria:**

- THE SYSTEM SHALL support a `--since <ISO-8601-date>` flag that limits re-fetching to pages whose last-modified header (or ETag) indicates a change since that date.
- IF a source page has no last-modified header, THE SYSTEM SHALL re-fetch it unconditionally when `--since` is used and log that the page had no cache signal.
- THE SYSTEM SHALL support a `--force` flag that re-fetches all pages regardless of cache signals.

---

### REQ-CI-09 — Configurable rate limiting

**User story:** As the operator, I want ingestion to rate-limit its requests, so that the adapter does not place unreasonable load on Purdue's servers.

**Acceptance criteria:**

- THE SYSTEM SHALL default to no more than 1 request per second to `catalog.purdue.edu`.
- THE SYSTEM SHALL make the rate limit configurable via a configuration file or environment variable.
- THE SYSTEM SHALL honour `Retry-After` headers on HTTP 429 responses.
