# Granular Curriculum Knowledge Mapping — Project Definition

**Status:** pre-requirements. This document fixes scope, vocabulary, decisions
and constraints so that requirements work has a settled foundation and does not
relitigate ground already covered.

**Domain:** computer science and engineering curricula in higher education.

**Kiro usage note:** this document is written to serve as steering context
(`.kiro/steering/product.md` and `.kiro/steering/structure.md`) for a Kiro spec
session, not as a spec itself. Section 6 is deliberately pre-formatted in EARS
notation so each capability can be handed to Kiro's requirements phase almost
unchanged; section 5.2 is written as enforceable rules for the same reason.
Section headers are kept stable so Kiro can be pointed at a specific section
(e.g. "steering §5.2") without re-deriving context each session.

---

## 1. Problem

Universities publish curricula as documents intended for human readers. Course
descriptions, requirement rules and programme structures exist as prose on
catalogue websites. The relationships between them — which concepts a course
actually teaches, which of those a student has already met elsewhere, what a
given course counts toward — are either buried in that prose or not written down
at all.

The consequences fall on students. They repeat learning they already hold, take
courses whose relevance to their goals nobody can articulate, and discover late
that a requirement was not satisfied. Advisors compensate manually and
inconsistently. Credit recognition between institutions is a slow human
negotiation over whether one course resembles another.

The underlying gap is that no machine-readable map exists at the level where
these questions are actually answered: the level of individual concepts.

---

## 2. What this project builds

A system that ingests published university curricula, produces a two-layer
knowledge map, and answers a small set of advisory questions from it.

**Layer one — the structural record.** Programmes, courses, requirement rules
and the relationships the institution itself publishes. Derived by deterministic
parsing. Auditable back to a source page with a retrieval date.

**Layer two — the concept graph.** Concepts extracted from course prose,
aligned to a controlled disciplinary vocabulary, with dependency relationships
between them. Produced by inference. Probabilistic, and treated as such
everywhere it is used.

**The advisory surface.** A small number of read-only queries over both layers,
answering questions about the curriculum. Not about any person.

---

## 3. Scope

### 3.1 In scope

Each in-scope item below is a candidate Kiro spec (its own
`requirements.md` / `design.md` / `tasks.md` triple), not a single monolithic
spec:

- Ingest from at least two institutions on two different catalogue platforms
  → spec: `catalogue-ingestion`
- A canonical intermediate schema that all adapters target
  → spec: `canonical-schema`
- Deterministic extraction of programmes, courses, requirement rules and
  declared relationships → spec: `catalogue-ingestion` (adapter sub-tasks)
- Concept extraction from course descriptions, aligned to a controlled
  vocabulary → spec: `concept-extraction`
- Inference of concept-level dependencies not declared by any source
  → spec: `concept-graph-inference`
- Five advisory queries (section 6) → spec: `advisory-queries`
- An evaluation harness measuring the inference layer against held-out ground
  truth → spec: `evaluation-harness`

### 3.2 Explicitly out of scope

Each of these was considered and cut deliberately. They are not backlog items
awaiting time; they are decisions. A Kiro requirements session for any spec
above must not silently reintroduce one of these as an acceptance criterion —
treat this table as a rejection list to check new criteria against.

| Excluded | Reason |
|---|---|
| Syllabi as a core input | Least portable input available. Availability varies from good to zero across institutions and correlates with department size and instructor habit, which would confound any cross-institution claim. Retained as an optional enrichment and as a planned ablation, never as a dependency. |
| Any registrar-authority claim | The project cannot mint identifiers on an institution's behalf. Encoded as a schema field, not a disclaimer. |
| Multi-tenancy | Adds operational surface with no bearing on the central claim. |
| UI beyond displaying a query result | The contribution is the mapping and its measurement, not an interface. |
| Credential issuance | Requires institutional authority and assessment data, neither of which exists here. See section 7. |
| Student records of any kind | The system holds no persistent data about any person. See section 5.3. |

### 3.3 Deferred, with a stated gate

- **Micro-credential support.** Direction the architecture must not preclude.
  No learner or achievement types are added until the inference layer has a
  measured quality figure. Do not open a Kiro spec for this until the gate in
  §12 (evaluation harness result) is met.
- **Conversational intent elicitation** (section 6.6). Same gate.

---

## 4. Vocabulary

Requirements work depends on these terms being used consistently. Kiro
requirements sessions should reuse these terms verbatim rather than
re-deriving synonyms — inconsistent vocabulary across specs is the main way
this kind of project drifts.

**Declared** — a fact the institution publishes. A prerequisite listed in a
catalogue, a programme's course list, a cross-listing. Ground truth. Auditable
to a URL.

**Inferred** — a fact the system produced. An extracted concept, a concept
dependency, an overlap estimate. Probabilistic. Never merged with declared
facts, and never presented as if it were one.

**Concept / granular knowledge** — an atomic unit of learning content, finer
than a course. "Maximum likelihood estimation" rather than "CS 229".

**Knowledge unit** — a concept identifier in the controlled vocabulary
(section 8.2). The unit of cross-institution identity.

**Course set** — a named group of courses a requirement draws from, e.g. "CS
Courses Numbered 110 and Above". Institutions frequently name these; the
requirement references the set rather than enumerating courses.

**Open enumeration** — a course set the source states open-endedly ("CS247,
CS247B, CS247G, etc."). Cannot be given a closed identifier set. Flagged
explicitly because it appears in documents that otherwise function as
authoritative.

**Adapter** — the per-platform component that parses one institution's
catalogue into the canonical schema. Adapters parse and nothing else: no
inference, no model calls.

**Authority** — whether an identifier was issued by an institution's system of
record (`registrar`) or minted by this pipeline (`derived`). Defaults to
`derived` and is a field on every minted item.

**Machine-checkable** — a requirement rule successfully structured into a
predicate. Rules that resist structuring are marked
`not_machine_checkable` and surfaced, never silently dropped.

---

## 5. Architecture

### 5.1 Three-stage shape

```
   catalogue sources          canonical schema           consumers
   ─────────────────          ────────────────           ─────────
   Institution A  ──┐
    (platform 1)    ├── adapter ──┐
                    │             │
   Institution B  ──┘             ├──▶  Programme          ┌─▶ CASE minting
    (platform 2) ───── adapter ──┘      Course             │
                                        Requirement    ────┤
                                        CourseSet          │
                                        DeclaredEdge       └─▶ concept graph
                                                                 │
                                                                 ▼
                                                            advisory queries
```

Genericity lives entirely at the adapter boundary. Nothing downstream of the
canonical schema knows which platform a record came from. This is the central
architectural bet, and it is why the MVP requires two institutions on two
platforms — the abstraction is unfalsifiable at one.

### 5.2 Enforced invariants

Implemented as constructor-level validators rather than documented conventions,
so no code path can bypass them. These are written as standing constraints
because every Kiro spec's `design.md` for this project must satisfy all of
them; a design that violates one of these is wrong regardless of which spec
it belongs to.

- Every record carries provenance: source URL, retrieval timestamp, adapter
  name and version, and the source's own revision identifier where it states
  one.
- Declared and inferred facts are separate types and cannot be merged.
- Concepts produced by a model must record the model identifier.
- Minted identifiers carry `authority: derived` unless genuinely issued by an
  institution.
- Requirements marked unstructured must retain their verbatim source text.

### 5.3 Learner state

There is deliberately no learner type and no achievement type. What a student
has completed is supplied as an immutable, session-scoped input to a query and
is never persisted, never returned inside an answer, and carries no identity
field.

This is a structural guarantee rather than a policy: the system cannot become a
student record because it has nowhere to put one. It is also what allows the
project to proceed without institutional data agreements.

### 5.4 Storage

Development runs on local Neo4j with pgvector, matching the maintained local
development environment of the graph toolkit. Connection details live in
configuration so promotion to a managed graph store is a config change rather
than a rewrite.

Two constraints found during evaluation of options:

- The FalkorDB graph store does not support traversal-based search. Prerequisite
  tracing is a traversal, so FalkorDB is unsuitable as the primary store.
- Managed cloud graph stores in this family have a substantial minimum
  configuration and no small tier, making them unsuitable for iterative
  development.

An open question (section 10) is whether a full GraphRAG stack is warranted at
all, given the advisory surface has no conversational interface.

---

## 6. Capabilities

Written as user stories with EARS-notation acceptance criteria so each can be
pasted into a Kiro `requirements.md` with minimal rework. Every answer
declares its evidence basis — `declared`, `inferred` or `mixed` — and answers
containing inference must carry a confidence and a caveat.

### 6.1 Credit consequence — spec: `advisory-queries` / credit-consequence

*As a student or advisor, I want to know what a given course counts toward,
so that I can plan around published requirements rather than guessing.*

**Declared only, structurally enforced.** Built from published programme
membership relationships. The strongest statement the system makes, because it
restates the institution's own position rather than offering an opinion about
it.

Acceptance criteria:
- WHEN a user queries what a course counts toward, THE SYSTEM SHALL return
  only relationships present in the declared layer.
- IF no declared membership relationship exists for the course, THEN THE
  SYSTEM SHALL report that no credit relationship is published, rather than
  inferring one.
- WHEN an answer is returned, THE SYSTEM SHALL label its evidence basis as
  `declared`.

### 6.2 Overlap — spec: `advisory-queries` / overlap

*As a student, I want to know whether a target course covers concepts I've
already met, and which concepts it doesn't, so that I can judge relevance
without assuming exemption.*

**Inferred.** Reports concepts in a target course that appear covered by
courses already completed, *and the gaps* — the concepts with no supporting
evidence. Gaps are usually the more useful half.

Acceptance criteria:
- WHEN a user queries overlap for a target course against a supplied
  completed-course list, THE SYSTEM SHALL return both matched concepts and
  unmatched (gap) concepts.
- WHEN an overlap answer is rendered, THE SYSTEM SHALL attach a confidence
  score and a caveat, and SHALL label the evidence basis as `inferred`.
- THE SYSTEM SHALL NOT use entitlement language (e.g. "exempt", "you can
  skip") anywhere in an overlap answer; this SHALL be enforced as a rendering
  check, not a style guideline.
- WHEN the completed-course list is supplied, THE SYSTEM SHALL treat it as a
  session-scoped input and SHALL NOT persist it after the query completes.

### 6.3 Readiness — spec: `advisory-queries` / readiness

*As a student, I want to know whether I can take a course given what I've
completed, so that I can plan enrollment.*

**Declared.**

Acceptance criteria:
- WHEN a user queries readiness for a course, THE SYSTEM SHALL return the
  set of unmet prerequisites drawn from the declared layer.
- WHEN an unmet prerequisite is returned, THE SYSTEM SHALL include the
  catalogue's verbatim wording alongside the structured result.

### 6.4 Unlock — spec: `advisory-queries` / unlock

*As a student, I want to know what a course opens up, so that I can see the
forward consequence of taking it.*

**Declared.**

Acceptance criteria:
- WHEN a user queries unlock for a course, THE SYSTEM SHALL perform a forward
  prerequisite traversal over declared edges only and return the resulting
  course set.

### 6.5 Programme fit — spec: `advisory-queries` / programme-fit

*As a student or advisor, I want to know how far a course or plan would move
me through a programme, so that I can gauge progress honestly.*

**Declared where rules structured; explicitly incomplete otherwise.**

Acceptance criteria:
- WHEN a programme-fit answer is computed, THE SYSTEM SHALL report the share
  of requirement rules that could not be structured (`not_machine_checkable`)
  alongside the progress figure.
- THE SYSTEM SHALL NOT render a progress indicator that omits the
  unstructured-rule share.

### 6.6 Interest-driven discovery *(deferred — do not open a Kiro spec yet)*

*As a prospective or current student, I want to state an interest and see
which courses cover it, so that I can plan without first assembling a
transcript.*

Gated behind §3.3 and §12. If built:

Acceptance criteria (for future use, not current implementation):
- WHEN a user states an interest, THE SYSTEM SHALL resolve it to one or more
  controlled-vocabulary knowledge units before matching, and SHALL NOT match
  against free text.
- WHEN a course is returned as a match, THE SYSTEM SHALL report coverage as a
  count (e.g. "8 of 11 concepts") rather than an unqualified fitness claim.
- IF coverage of the stated interest is thin across the extracted graph, THEN
  THE SYSTEM SHALL disclose this rather than omitting weakly-covered results.

---

## 7. Why advisory and not credentialling

Micro-credential issuance was examined and rejected for the MVP.

Issuance is a solved problem — several platforms issue standards-conformant
badges today, and anyone can mint one. The unmet need is *recognition*: what a
credential actually counts for. That is the question the declared layer answers,
which is why the value here is as an evidence layer, not a badging platform.

Two blockers make issuance unavailable regardless:

**Authority.** A credential is a claim about a person, not a description of a
course. A wrong course mapping is a data-quality bug; a wrong credential has
consequences for a student. This requires institutional authority the project
does not have.

**Assessment granularity.** Institutions assess at course level. A course grade
says nothing about which concepts a student mastered. A concept-level credential
inferred from a course grade asserts eighteen specific competencies on the
evidence of one passing mark — false precision, and worse than being coarse
honestly.

**Resolution:** concept-level *evidence*, coarser *claims*. Granular knowledge
is the internal representation that performs matching, equivalence and gap
analysis. Any claim asserts only what the underlying assessment can carry.

Should concept-level claims become a goal, the wedge is a partner whose
assessment is already concept-tagged — mastery-based courses, adaptive
platforms, certification exams publishing item-to-objective maps. A much smaller
universe than "institutions with catalogues", which is worth knowing in advance.

---

## 8. Concept identity

### 8.1 The problem

Concept identifiers minted per institution do not match across institutions.
"MLE" and "maximum likelihood estimation" are the same concept under different
names; "logistic regression" and "linear regression" are different concepts with
near-identical embeddings. Cosine similarity cannot separate *same concept,
different name* from *different concepts, same neighbourhood*, because both sit
at the same similarity range. Related failure modes: hierarchy reads as synonymy,
and contrast reads as similarity.

For an advisory system the costs are asymmetric — a false merge tells a student
they have covered something they have not — so matching biases toward precision.

### 8.2 Resolution: align to a controlled vocabulary

Do not match institution to institution. Align each institution independently to
a shared external vocabulary; two concepts match if and only if both resolve to
the same knowledge unit.

For computing, ACM/IEEE-CS/AAAI's CS2023 provides this: seventeen knowledge
areas decomposed into knowledge units and topics, with core/elective tiering and
hour allocations, and disciplinary authority behind it.

Four benefits. Identity comes from the vocabulary rather than a distance score.
Alignment is linear in institutions rather than quadratic in pairs. The
alignment table is inspectable, so errors are locatable. And the resulting claim
is defensible to a registrar in a way a cosine score is not.

### 8.3 Matching pipeline — spec: `concept-extraction` / vocabulary-alignment

Written here as ordered pipeline stages because this is the sequence a Kiro
`design.md` for the `concept-extraction` spec should reproduce as its
component breakdown.

1. **Retrieve** — embed concept text alone; retrieve top-k candidate knowledge
   units. Embeddings do retrieval, never adjudication.
2. **Rerank on metadata** — co-occurrence with neighbouring concepts (the
   strongest signal, since it carries information the string does not),
   normalised course level as a depth proxy, department as a soft prior only.
3. **Reject on structure** — an alignment implying a dependency cycle or a
   prerequisite ordering violation is wrong regardless of similarity.
   Constraints permit rejection, which the cost asymmetry favours.
4. **Verify** — constrained selection among retrieved candidates, which is far
   more reliable than open-ended extraction.

Constraints on the pipeline, written as acceptance-criteria-style rules for
the same reason:
- THE SYSTEM SHALL NOT concatenate metadata into embedded text; metadata SHALL
  be used only at the reranking stage.
- THE SYSTEM SHALL NOT use department as a hard filter at any stage, given
  pervasive cross-listing. This SHALL be covered by an explicit regression
  test in the `evaluation-harness` spec.

---

## 9. Sources and access

| Source | Access | Notes |
|---|---|---|
| Institutional catalogue web pages | Public, robots-permitting | Primary source. Verify robots.txt per institution; permission varies within a single university's estate. |
| Catalogue vendor APIs | Per-tenant, key-issued by the institution | Structured and preferable, but requires an institutional relationship. Not currently available. |
| Archived catalogue years | Public where the platform exposes them | Some platforms publish a decade of prior catalogues, enabling curriculum drift analysis. |
| Curriculum proposal systems | SSO-gated | Hold uploaded syllabi. Institutional access only. |
| Student information systems | Authenticated, institutional | Out of reach and out of scope. |

**Access findings that shape the design.** One major university's structured
course API is robots-disallowed while its catalogue website permits fetching —
permission does not follow data richness. Vendor-hosted catalogues share
identical URL structures across hundreds of institutions, so a single adapter
serves many, which is a stronger genericity result than two bespoke adapters.
Public catalogue pages remain the only source available without an institutional
relationship, which is the normal starting position rather than a setback.

---

## 10. Open questions

1. **Research artefact or product.** Defaulted to research artefact: keeps the
   evaluation central and permits hard-coded adapters. Affects whether the
   structural export must withstand registrar scrutiny and whether adapter
   count must look extensible.
2. **Does a full GraphRAG stack earn its place?** The advisory surface is five
   structured queries plus one fuzzy-matching step — a graph database workload
   with a vector index, not a retrieval-augmented generation workload. The
   original architecture assumed GraphRAG because it assumed a conversational
   tutoring interface, which the current scope does not have. If interest-driven
   discovery (6.6) is built, the assumption returns with it.
3. **Which second institution**, and whether one adapter serving many
   vendor-hosted catalogues counts as one adapter or several for the purposes of
   the genericity claim.
4. **Granularity floor.** How fine concepts should go. Provisionally: the grain
   at which the controlled vocabulary defines knowledge units, with the source's
   own grain recorded rather than normalised away.

---

## 11. Evaluation — spec: `evaluation-harness`

Detailed method is covered in the companion methodology document. In summary:

**Headline metric — held-out declared relationships.** Withhold published
prerequisite relationships from the inference pipeline, build the concept graph
from descriptions alone, and measure whether inferred concept dependencies
recover them. No hand-labelling, no gold set, and no opinion can move the
number.

**Reproduction versus contribution reported separately.** Inferred
relationships that merely reproduce published ones show the pipeline runs.
Relationships never declared anywhere, and confirmed by a domain expert, are the
actual contribution.

**Expert judgement, blinded.** The builder is also the domain expert, which is
the standard route to a flattering result. Generated relationships are judged
mixed with plausible distractors, blind, against a rubric written before any
output is seen. Per-item confidence is recorded so results can be reported
stratified by subdomain rather than as uniform expert assertion.

**Ablation.** Retrieval alone, plus metadata reranking, plus structural
rejection — so each component's contribution is a number rather than an
assumption.

**Failure reporting.** The share of requirement rules that could not be
structured, the share of model outputs rejected by validation, and the
subdomains where accuracy was poor are reported alongside successes.

**Scope of the claim.** Two institutions in one discipline tests adapter
genericity, not extraction genericity — computer science course prose is
unusually enumerative, and what works on it may not transfer to discursive
catalogue writing. The defensible claim is *generic across institutions,
demonstrated within computer science*.

**Gate this evaluation controls (see §3.3):** micro-credential support and
interest-driven discovery (§6.6) may not become Kiro specs until this
harness produces a measured quality figure for the inference layer.

---

## 12. Principal risks

| Risk | Consequence | Mitigation |
|---|---|---|
| Concept extraction quality is poor | Every downstream capability rests on sand | Measured before anything is built on it; gate on the held-out metric |
| Self-evaluation flatters the system | Results do not survive outside scrutiny | Blinding, pre-written rubric, mechanical headline metric |
| Uneven description granularity across course types | Sparse graph over project and studio courses | Measure and report the variance rather than assume uniformity; syllabus ablation quantifies the gap |
| Source access withdrawn or restructured | Ingest breaks | Deterministic parsers fail loudly; provenance makes staleness visible |
| Advisory output misread as entitlement | Student acts on it and is harmed | Structural phrasing guard; gaps reported alongside overlaps; declared and inferred never conflated |
| Scope drift toward credentialling | Consequential layer built on unmeasured foundation | No learner or achievement types until the gate in 3.3 is passed |

---

## 13. Suggested Kiro spec breakdown

Recommended order of Kiro spec sessions, each producing its own
`requirements.md` / `design.md` / `tasks.md`, given the dependency shape
above (schema before adapters; adapters before extraction; extraction before
inference; inference gated by evaluation before advisory queries ship
inferred answers):

1. `canonical-schema` — §5, §5.2 invariants as design constraints
2. `catalogue-ingestion` — §3.1, §9; two adapters, two platforms
3. `concept-extraction` — §8; vocabulary alignment pipeline
4. `concept-graph-inference` — §2 layer two, dependency inference
5. `evaluation-harness` — §11; must run before `advisory-queries` §6.2/6.5
   accept inferred answers as done
6. `advisory-queries` — §6.1–6.5 (6.6 excluded until §3.3 gate clears)

Each session should be pointed at this document's relevant section rather
than re-explaining context in the prompt.
