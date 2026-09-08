---
inclusion: always
---

# Granular — Settled Decisions

This file records decisions made during the requirements clarification session. These are not open questions. A Kiro spec session must not relitigate them.

## Institution and platform

- **Single institution:** Purdue University (undergraduate and graduate CS courses)
- **Single platform:** Modern Campus Acalog — `catalog.purdue.edu`
- **Secondary structured source:** purdue.io OData v4 API (community-built, open, no authentication required)
- The original project definition required two institutions on two different platforms. This constraint is deliberately relaxed. The genericity claim is scoped to: one adapter serving the Modern Campus platform, which hosts many institutions — adapter genericity is demonstrated by platform coverage, not institution count.

## Scope changes from original project definition

| Original decision | Revised decision | Reason |
| --- | --- | --- |
| §6.6 interest-driven discovery deferred behind evaluation gate | **Lifted — built from the start as the primary capability** | It is the primary user-facing value of the system |
| No UI beyond displaying a query result | **Next.js + TypeScript frontend** | Required to support the student interaction model |
| No student records or persistence | **Confirmed — session-scoped only, nothing persisted** | Structural guarantee maintained |
| Administrator analytics | **Removed from scope** | Simplified out |
| Student course selection persistence | **Removed from scope** | Session-scoped only |
| Two institutions on two platforms | **One institution, one platform** | Scope focused on Purdue CS |

## Primary capability definition

Interest-driven discovery:

1. Student submits a plain-English description of what they want to learn
2. System resolves the description to CS2023 knowledge units (controlled vocabulary — never free-text matching)
3. System finds courses whose concept graph covers those knowledge units
4. System returns a prioritised list of courses with:
   - **Relevance score** — match quality between query concepts and course concepts
   - **Coverage breadth** — count format: "N of M concepts covered"
5. If coverage across the graph is thin, the system discloses this rather than omitting weakly-covered results
6. No entitlement language anywhere in any answer (enforced as a rendering check)
7. The query input is session-scoped and not persisted

## Advisory queries (secondary — not the first spec)

All five §6 queries remain in scope after the primary capability is built:

- §6.1 Credit consequence (declared)
- §6.2 Overlap (inferred)
- §6.3 Readiness (declared)
- §6.4 Unlock (declared)
- §6.5 Programme fit (declared + structured)

## CS2023 vocabulary

- No machine-readable version exists publicly
- Bootstrapped from the published ACM/IEEE-CS/AAAI PDF as a one-time task in the `concept-extraction` spec
- This bootstrap task produces the authoritative seed file used by all downstream alignment

## Technology stack

- Frontend: Next.js with TypeScript
- Backend: Python
- Graph store: Neo4j (local, provisioned by project setup scripts)
- Vector index: pgvector (local, provisioned by project setup scripts)
- Connection details in configuration — promotion to managed store is a config change

## Research artefact framing

- Hard-coded Purdue/Modern Campus adapter is acceptable
- Loud failures preferred over silent degradation
- Gaps and failure rates documented and reported
- Registrar-grade robustness not required
