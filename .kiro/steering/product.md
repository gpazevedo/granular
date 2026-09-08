---
inclusion: always
---

# Granular — Product Steering

## What this project builds

A system that ingests Purdue University's published CS curriculum (undergraduate and graduate), produces a two-layer knowledge map, and answers student queries about what to learn next.

**Layer one — the structural record.** Programmes, courses, requirement rules and the relationships the institution publishes. Derived by deterministic parsing. Auditable back to a source page with a retrieval date.

**Layer two — the concept graph.** Concepts extracted from course prose, aligned to the CS2023 controlled vocabulary (ACM/IEEE-CS/AAAI), with dependency relationships between them. Produced by inference. Probabilistic, and treated as such everywhere it is used.

**The primary advisory surface.** A student describes in plain English what they want to learn. The system resolves that description to CS2023 knowledge units, finds courses whose concept graph covers those units, and returns a prioritised list with two metrics per course:

- **Relevance score** — how well the course's concepts match what the student asked for
- **Coverage breadth** — how many of the matched concepts the course covers (e.g. "8 of 11 concepts")

No answer uses entitlement language. Declared and inferred facts are never conflated.

## Primary capability

Interest-driven discovery: plain-English interest → prioritised course list with relevance + coverage metrics.

## Secondary capabilities (not the first spec, but in scope)

- Credit consequence: what a course counts toward (declared only)
- Overlap: concepts a student has already met vs. gaps in a target course (inferred)
- Readiness: unmet prerequisites for a course (declared)
- Unlock: forward prerequisite traversal (declared)
- Programme fit: progress through a programme's requirement rules (declared + structured)

## Out of scope (deliberate cuts — do not reintroduce)

| Excluded | Reason |
| --- | --- |
| Student records or persistent session data | Structural guarantee: the system has nowhere to store them |
| Administrator analytics | Simplified out of MVP scope |
| Student course selection persistence | Session-scoped only |
| Credential or badge issuance | Requires institutional authority |
| Multi-tenancy | No bearing on the central claim |
| Syllabi as a core input | Not portable enough across institutions |
| Any registrar-authority claim | Cannot mint identifiers on behalf of an institution |

## Source

# [[file:project_definition_kiro.md]]
