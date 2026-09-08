---
inclusion: always
---

# Granular — Architecture and Invariants Steering

## Stack

- **Frontend:** Next.js + TypeScript
- **Backend:** Python
- **Graph store:** Neo4j (local, provisioned by project setup)
- **Vector index:** pgvector (local, provisioned by project setup)
- **Catalogue source:** Purdue University — Modern Campus Acalog (`catalog.purdue.edu`)
- **Secondary source:** purdue.io OData v4 API (community-built, open)
- **Controlled vocabulary:** CS2023 (ACM/IEEE-CS/AAAI) — bootstrapped from published PDF as a one-time task in the `concept-extraction` spec

## Three-stage shape

```text
   catalogue sources          canonical schema           consumers
   ─────────────────          ────────────────           ─────────
   catalog.purdue.edu  ──┐
                         ├── Purdue/MC adapter ──▶  Programme         ┌─▶ concept graph
   purdue.io OData    ───┘                            Course          │      │
                                                      Requirement     │      ▼
                                                      CourseSet       │  advisory queries
                                                      DeclaredEdge ───┘      │
                                                                             ▼
                                                                       Next.js frontend
```

Genericity lives at the adapter boundary. Nothing downstream of the canonical schema knows which source a record came from.

## Enforced invariants

These are constructor-level constraints, not conventions. Every spec's `design.md` must satisfy all of them. A design that violates one is wrong regardless of which spec it belongs to.

1. **Provenance on every record:** source URL, retrieval timestamp, adapter name and version, and the source's own revision identifier where stated.
2. **Declared and inferred facts are separate types** and cannot be merged. They cannot appear in the same field of any schema object.
3. **Concepts produced by a model must record the model identifier.**
4. **Minted identifiers carry `authority: derived`** unless genuinely issued by an institution.
5. **Requirements marked unstructured must retain their verbatim source text.** They are surfaced, never silently dropped.

## Learner state invariant

There is no learner type and no achievement type. A completed-course list supplied to a query is:

- Session-scoped only
- Never persisted after the query completes
- Never returned inside an answer
- Carries no identity field

This is a structural guarantee, not a policy.

## Storage constraints

- FalkorDB is unsuitable as the primary graph store (does not support traversal-based search; prerequisite tracing requires traversal).
- Managed cloud graph stores are unsuitable for iterative development (no small tier).
- Connection details live in configuration so promotion to a managed store is a config change, not a rewrite.

## Research artefact framing

This is a research artefact, not a production system. Specifically:

- Hard-coded adapter for Purdue/Modern Campus is acceptable
- Loud failures on unexpected catalogue structure are preferred over silent degradation
- Gaps and failure rates are documented and reported, not hidden
- Registrar-grade robustness is not required

## Spec dependency order

1. `canonical-schema` — schema types and invariants
2. `catalogue-ingestion` — Purdue/Modern Campus adapter
3. `concept-extraction` — CS2023 bootstrap + alignment pipeline
4. `concept-graph-inference` — dependency inference
5. `evaluation-harness` — held-out metric (gates nothing in current scope since §6.6 deferral is lifted)
6. `advisory-queries` — interest-driven discovery + secondary queries

## Vocabulary (use verbatim, do not re-derive synonyms)

- **Declared** — a fact the institution publishes. Auditable to a URL.
- **Inferred** — a fact the system produced. Probabilistic. Never merged with declared facts.
- **Concept / granular knowledge** — an atomic unit of learning content, finer than a course.
- **Knowledge unit** — a concept identifier in the CS2023 controlled vocabulary.
- **Course set** — a named group of courses a requirement draws from.
- **Open enumeration** — a course set stated open-endedly; cannot be given a closed identifier set.
- **Adapter** — the per-platform component that parses one institution's catalogue into the canonical schema. Adapters parse and nothing else: no inference, no model calls.
- **Authority** — whether an identifier was issued by an institution's system of record (`registrar`) or minted by this pipeline (`derived`).
- **Machine-checkable** — a requirement rule successfully structured into a predicate.
