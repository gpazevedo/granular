# Architecture Decisions

This document collects the architectural decisions taken while building Granular
and, for each one, the reasoning behind it. It is a companion to
[`SYSTEM_OVERVIEW.md`](SYSTEM_OVERVIEW.md) (what was built) and
[`.kiro/steering/decisions.md`](.kiro/steering/decisions.md) (the scope decisions
settled during requirements clarification) — this file focuses on *why* the
system is shaped the way it is, pulling context from both plus the per-package
`design.md` files under [`.kiro/specs/`](.kiro/specs/).

**Framing to read every decision against:** Granular is a research artefact
that models a solution to the problem "map courses to a student's plain-English
intent." It is explicitly **not** a production system — see
[Decision 1](#1-research-artefact-not-a-production-system). Several choices
below trade robustness or completeness for the ability to iterate fast and
demonstrate the core idea cleanly.

---

## 1. Research artefact, not a production system

**Decision:** Build for a single institution/platform, accept hard-coded
adapters, prefer loud failures over silent degradation, and skip registrar-grade
robustness.

**Why:** The goal is to *model and validate* a two-layer curriculum
representation and an intent-resolution query surface — not to operate a
production advising system. Every hour spent on institutional generality or
defensive robustness is an hour not spent validating whether the core idea
(declared structure + inferred concept graph → plain-English discovery) works
and produces trustworthy results.

**Consequences:** Gaps and failure rates are measured and reported rather than
hidden (see the evaluation harness, [Decision 10](#10-evaluation-harness-reports-separate-honest-numbers-not-one-score)),
and an unstructured requirement rule or a rejected model output is a reportable
event, not a bug to be swallowed. See
[`.kiro/steering/decisions.md`](.kiro/steering/decisions.md) → "Research
artefact framing."

---

## 2. Scope narrowed from two institutions/platforms to one

**Decision:** Target a single institution (Purdue University) on a single
platform (Modern Campus Acalog), with purdue.io's OData v4 API as a secondary
structured source. The original brief called for two institutions on two
different platforms.

**Why:** Modern Campus hosts many institutions, so genericity is demonstrated
at the *platform* level (one adapter, many potential institutions) rather than
by institution count. Building and validating a second full adapter for a
second platform would have doubled ingestion effort without adding evidence for
the part of the system actually being tested — concept extraction, alignment,
and inference.

**Consequences:** The genericity claim is scoped precisely: "adapter genericity
across the Modern Campus platform, not extraction genericity across
disciplines" — this caveat is templated into every evaluation report so it
can't be overstated by accident. A second adapter (UIUC, static catalogue) was
still built for fast local iteration without depending on Purdue's live site,
but it doesn't broaden the genericity claim.

---

## 3. Interest-driven discovery promoted from deferred to primary capability

**Decision:** The original project definition deferred interest-driven
discovery (§6.6) behind an evaluation-quality gate. That gate was lifted;
discovery was built from the start as the primary capability, and the
evaluation harness itself was demoted to "informs trust in the graph" rather
than "blocks shipping."

**Why:** Interest-driven discovery — "here's what I want to learn, what should
I take?" — is the actual user-facing value proposition of the system. Gating
its existence behind a graph-quality threshold would have meant potentially
never seeing the primary capability work end-to-end. Building it early, with
the evaluation harness running in parallel and reporting honestly on quality,
surfaces integration problems sooner.

**Consequences:** The evaluation harness (`granular-eval`) reads Neo4j and
writes nothing back; it exists to characterize graph quality, not to gate a
release. See [`.kiro/steering/decisions.md`](.kiro/steering/decisions.md) →
"Scope changes from original project definition."

---

## 4. Declared and inferred facts are separate types everywhere

**Decision:** The structural record (declared) and the concept graph
(inferred) are modeled as distinct schema types. They cannot be merged into the
same field of any record — this is enforced as a constructor-level constraint,
not a naming convention.

**Why:** The whole trust model of the system rests on a student being able to
tell the difference between "the institution published this" (auditable to a
source URL and retrieval date) and "the system inferred this" (probabilistic,
derived from LLM extraction + embedding alignment + structural scoring). If the
two could ever occupy the same field, any answer built on top could silently
present a guess as a fact.

**Consequences:** Every downstream consumer (advisory queries, the Discover
surface) has to explicitly choose which layer it's drawing from, which keeps
answers honest about their own confidence. See
[`.kiro/steering/structure.md`](.kiro/steering/structure.md) → "Enforced
invariants."

---

## 5. No learner/achievement state — session-scoped only

**Decision:** There is no learner type and no achievement type anywhere in the
schema. A completed-course list supplied with a query is used only for that
query, never persisted, never returned in an answer, and carries no identity
field.

**Why:** This is a structural guarantee that the system cannot become a system
of record for student progress, and it removes an entire class of privacy and
data-retention concerns that would otherwise need separate defensive handling.
It also matches the out-of-scope cuts made early (no student records, no
administrator analytics, no course-selection persistence) — see
[`.kiro/steering/product.md`](.kiro/steering/product.md) → "Out of scope."

**Consequences:** Advisory queries that logically depend on "what has this
student already completed" (overlap, readiness) accept that list as an
ephemeral query parameter every time, never as a lookup against stored state.

---

## 6. No entitlement language in any answer

**Decision:** Every advisory answer reports two metrics — relevance score and
coverage breadth ("N of M concepts covered") — and is passed through an
`EntitlementLanguageGuard` before being returned. No answer says a student
"can," "should," "is allowed to," or "will" take/pass/complete anything.

**Why:** The system has no institutional authority. It has no visibility into
enrollment rules, seat availability, academic standing, or override
permissions, so any language implying entitlement or permission would be a
claim the system cannot actually back. Confining answers to match-quality and
coverage-count keeps every claim inside what the concept graph can actually
support.

**Consequences:** The guard is a rendering-time enforcement point, not just a
prompt instruction — it runs as an explicit assertion step in the Discover flow
(see `SYSTEM_OVERVIEW.md` → "Discover query flow") so a language slip in an LLM
rerank step can't reach the student.

---

## 7. Storage: Neo4j + pgvector, openCypher only, no vendor extensions

**Decision:** Use Neo4j for the graph (structural record + concept graph) and
pgvector for embeddings, both running locally via the project's own setup
scripts. Every graph query is written in plain openCypher — no APOC, no Graph
Data Science library, no Neo4j-specific procedures.

**Why (Neo4j + pgvector split):** The system needs two genuinely different
query shapes — multi-hop traversal (prerequisite chains, dependency paths) and
nearest-neighbor similarity search (concept-to-knowledge-unit alignment,
query-to-concept matching). Neither store does both well, so the system uses
one of each rather than forcing one engine to do a job it's weak at.

**Why openCypher only:** Keeping every query portable to any openCypher-
compatible store (Amazon Neptune, Memgraph, and others) means the graph layer
isn't locked to Neo4j specifically — connection details live in configuration,
so promotion to a managed store is a config change, not a rewrite. This was a
deliberate choice to preserve optionality without spending effort building an
abstraction layer: plain openCypher already gets that portability for free.

**Why not FalkorDB:** Evaluated and rejected — it doesn't support the
traversal-based search that prerequisite tracing requires.

**Why not a managed cloud graph store for now:** No small/cheap tier exists
that fits iterative local development; local Neo4j + pgvector via Docker Compose
keeps the iteration loop fast and free. See
[`.kiro/steering/structure.md`](.kiro/steering/structure.md) → "Storage
constraints."

---

## 8. CS2023 as a controlled vocabulary, bootstrapped once from the source PDF

**Decision:** Concepts are never matched to courses as free text. Every
extracted concept is aligned to exactly one node in the CS2023 (ACM/IEEE-
CS/AAAI) controlled vocabulary, or left explicitly unaligned. Since no
machine-readable version of CS2023 exists publicly, the vocabulary is
bootstrapped once from the published PDF as a one-time parsing task, producing
the authoritative seed file every later run aligns against.

**Why:** A controlled vocabulary is what makes "coverage breadth" a meaningful,
comparable metric ("8 of 11 concepts") instead of an ad hoc string-similarity
score, and it's what lets the discover-relevance evaluation compare against
knowledge *areas* that stay stable across catalogue changes rather than
free-text labels that would drift.

**Consequences:** The one-time PDF bootstrap is a manual, auditable step, not a
pipeline stage that re-runs — vocabulary drift is a deliberate, visible event,
not something that happens silently on every ingestion run.

---

## 9. Concept alignment is a four-stage, narrowing-only pipeline

**Decision:** Each raw extracted concept moves through four stages — retrieve
(pgvector top-k), rerank (weighted structural/embedding score), reject (drop
candidates that would create a prerequisite-ordering violation), verify
(LLM cross-domain check) — where every stage is only allowed to narrow the
candidate set, never introduce new candidates.

**Why:** Splitting "generate candidates" from "judge candidates" from
"sanity-check the winner" makes each stage's failure mode independently
inspectable and testable, and the narrowing-only rule means a bug in a later
stage can never resurrect something an earlier stage already correctly
eliminated. It also means the expensive step (an LLM call in stage 4) only ever
runs on a single, already-cheaply-filtered survivor per concept — not on every
candidate.

**Why department is a soft prior (+0.05), never a hard filter:** Cross-listed
courses (e.g., a course counted as both CS and ECE) would be wrongly excluded
by a hard departmental filter even when the concept genuinely belongs. A small
constant prior lets department nudge the ranking without ever vetoing a
correct match. This is enforced by a standing regression test
(`REQ-EH-07`, `tests/evaluation/test_department_filter.py`) that reranks a
cross-listed course's candidates with the department signal zeroed out and
asserts the top choice doesn't change — a decision protected against silent
regression, not just documented.

**Why the stage-4 LLM verifier fails open:** Any LLM error or malformed
response is treated as "belongs." An LLM outage should never *narrow* the
candidate set further than the deterministic stages already did — treating an
infrastructure failure as a rejection would silently degrade coverage for a
reason that has nothing to do with alignment quality.

**Why the verifier exists at all:** Embedding similarity alone produces false
positives from lexical overlap — e.g. "solar car construction" scoring high
against the knowledge unit "Software Construction" purely on the shared word
"construction." An LLM check for genuine topical membership (not lexical
overlap) is the deliberate second opinion that catches this class of error; see
the case study in [Decision 12](#12-transparent-reporting-of-implementation-gaps-and-eval-driven-fixes).

---

## 10. Dependency inference is structural, never model-driven

**Decision:** The pipeline never calls a model to decide whether a dependency
edge exists between two concepts. Inference uses only structural signals —
course level, declared-prerequisite priors, knowledge-unit co-occurrence —
combined into a weighted score. Embedding similarity is used only to generate
candidates, never to decide an edge.

**Why:** Dependency edges carry causal claims ("you need A before B"), which is
a stronger claim than "A and B are topically similar." Restricting edge
decisions to structural signals derived from what the institution actually
declared (course numbering, prerequisite chains) keeps every inferred edge
traceable to a concrete, inspectable signal rather than an opaque model
judgment — important for a system whose central promise is that inferred facts
are clearly distinguishable from and accountable relative to declared ones.

**Why a hard filter on course level (never infer upward):** A dependency from a
lower-numbered course's concept onto a higher-numbered course's concept would
contradict the curriculum's own declared structure by construction — it's
rejected before scoring, not down-weighted, because there's no signal strong
enough to overturn a structural fact the institution already published.

**Why `min_dependency_score` was raised from 0.35 to 0.55:** The evaluation
harness showed the 0.40–0.50 confidence band held ~77% of all inferred edges
and was overwhelmingly false positive. Raising the threshold preserved
held-out recall (~0.483) while cutting false-positive-prone course pairs
roughly 10x — a concrete instance of the evaluation harness driving a pipeline
parameter change, not a guess.

**Why cycles are resolved by dropping the lowest-confidence edge:** A
dependency graph with a cycle is internally inconsistent (A depends on B
depends on A), and the score itself is the only signal available for which
edge is least trustworthy — so the cycle-breaking rule reuses the same scoring
the pipeline already trusts elsewhere, rather than introducing a second,
unrelated tie-breaking mechanism.

---

## 11. Discover query resolution: embedding retrieval + LLM rerank, fail-open

**Decision:** A plain-English query is first embedded and matched against
knowledge-unit embeddings in pgvector (top-k, similarity ≥ 0.3), then an LLM
call filters that candidate set down to genuinely matching knowledge units. If
the LLM call fails, the system falls back to the raw embedding-similarity set
rather than failing the query.

**Why two stages instead of one:** Embedding similarity alone is noisy at the
level of a single word or short phrase (the system overview's own example:
"machine learning" scoring close to "machine-level representation" purely on
token overlap). An LLM pass that reasons about intent, not just vector
distance, is the same "second opinion" pattern used in concept alignment
(Decision 9), applied to the query side instead of the concept side.

**Why fail-open here too:** An LLM outage during query resolution should
degrade *precision* (more candidates get through the embedding filter than
would ideally), not availability. Refusing the query outright because the
reranking model is down would be a worse outcome for the user than returning a
slightly noisier result set.

---

## 12. Transparent reporting of implementation gaps and eval-driven fixes

**Decision:** Where the shipped evaluation harness diverges from its original
spec — the `run` command's ablation section being a same-metric placeholder
rather than a true per-condition rerun, `split` being a stub, the `judge` track
having no CLI command, and the held-out split being drawn *after* inference
rather than before it — these gaps are documented explicitly in
`SYSTEM_OVERVIEW.md` rather than left implicit or silently worked around.

**Why:** This follows directly from the project's own "loud failures over
silent degradation" principle (Decision 1) applied to the evaluation system
itself: a report that quietly shows the same number for three ablation
conditions, or a headline F1 that reads as leakage-free when it isn't, would be
exactly the kind of overconfident number the harness exists to prevent
elsewhere in the pipeline. Documenting the gap costs nothing and prevents
someone from citing a number as stronger evidence than it is.

**Why the harness is five independent commands instead of one pipeline:**
`run`, `ablation`, `alignment`, and `discover` measure genuinely different
things (graph recovery, per-signal contribution, alignment-layer precision,
end-to-end query relevance) at different costs (`ablation` reruns scoring and
takes minutes; the others are cheap). Forcing them into one pipeline would mean
every invocation pays the cost of the slowest check even when only one number
is needed, and would blur which command's output actually backs which claim.

**Case study — the evaluation loop catching a real defect (commit sequence
`729e379` → `d8eb632` → `fe89591`):** adding the alignment-precision and
ablation evals surfaced two concrete problems — the stage-4 verifier accepting
cross-domain lexical matches (electrical-engineering "antenna" concepts passing
as CS networking, optics passing as graphics, statistics passing as
algorithms), and a shared acceptance threshold making the `retrieval_only`
ablation condition structurally unable to pass anything. Both were fixed at
the source (verifier prompt rewrite; per-mode threshold scaling) rather than
patched around. This is the harness performing its designed function: locating
a specific, fixable defect rather than producing one flattering aggregate
number.

---

## 13. Evaluation harness reports separate, honest numbers, not one score

**Decision:** Graph quality is measured as three deliberately separate
numbers — held-out declared-prerequisite recovery (mechanical), novel-edge
quality (blinded expert judgement), and per-stage contribution (ablation) —
plus first-class failure reporting (unstructured rules, rejected model
outputs, poor-coverage subdomains), always shown even when the count is zero.

**Why:** Folding these into one blended score would hide exactly the
information a reader needs to judge where to trust the graph and where not to:
a high score on declared-prerequisite recovery says nothing about whether the
*novel* edges (the pipeline's actual contribution beyond what the institution
already published) are any good, and an aggregate-only report can't reveal that
one knowledge area is being scored far worse than the rest. `REQ-EH-02`
explicitly disallows aggregate-only reporting for this reason.

**Consequences:** Every `run` writes a versioned, checksummed artefact
directory rather than overwriting a single file, so a number can never be
quietly re-generated with a different held-out split to look better after the
fact — reproducibility of the claim is itself part of the design.

---

## 14. Frontend: Next.js + TypeScript, added despite the original "no UI" scope

**Decision:** Build a real Next.js/TypeScript frontend rather than the
originally scoped "no UI beyond displaying a query result."

**Why:** Once interest-driven discovery was promoted to the primary capability
(Decision 3), a plain-English query box and a ranked, coverage-annotated
course list became the actual interaction the whole system exists to support —
a bare API response would not demonstrate the primary claim as legibly as a
usable UI does. See [`.kiro/steering/decisions.md`](.kiro/steering/decisions.md)
→ "Scope changes from original project definition."

---

## Where to look next

- [`SYSTEM_OVERVIEW.md`](SYSTEM_OVERVIEW.md) — diagrams and mechanics for every
  decision above
- [`.kiro/steering/decisions.md`](.kiro/steering/decisions.md),
  [`product.md`](.kiro/steering/product.md),
  [`structure.md`](.kiro/steering/structure.md) — the settled scope and
  invariants this document explains the reasoning behind
- [`.kiro/specs/*/design.md`](.kiro/specs/) — per-package design detail, including
  inline "why" notes referenced above
