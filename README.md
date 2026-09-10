# Granular

A research system that ingests a university's published CS curriculum, builds a
two-layer knowledge map — the declared structural record and an inferred
CS2023-aligned concept graph — and answers "what should I learn next?" queries in
plain English. Primary target institution/platform: Purdue University on Modern
Campus Acalog; a UIUC static-catalog adapter is also wired up for faster local
iteration.

## Documentation map

| Doc | What's in it |
| --- | --- |
| [`SYSTEM_OVERVIEW.md`](SYSTEM_OVERVIEW.md) | Architecture diagrams, the concept-alignment and dependency-inference pipelines, the Discover query flow, and a full description of the evaluation system |
| [`INFRASTRUCTURE.md`](INFRASTRUCTURE.md) | Full local setup: Docker services, `.env` reference, troubleshooting |
| [`DATA_LIFECYCLE.md`](DATA_LIFECYCLE.md) | What's persisted where, and the pipeline's read/write order |
| [`project_definition_kiro.md`](project_definition_kiro.md) | The original project brief this system was scoped from |
| [`.kiro/steering/`](.kiro/steering/) | Settled product scope, architecture invariants, and decisions — do not relitigate these in a spec session |
| [`.kiro/specs/`](.kiro/specs/) | Per-package requirements/design/tasks (spec-driven development) |

## Quickstart

```bash
# 1. Start Neo4j + pgvector
docker compose up -d

# 2. Configure secrets
cp .env.example .env   # fill in an LLM API key — see .env.example for provider options

# 3. Install the Python package (editable) into your virtualenv
pip install -e .

# 4. Run the pipeline, in order
granular-ingest uiuc --output-dir data/ingestion/uiuc   # or the acalog/purdue adapter
granular-extract run     # concept extraction + CS2023 alignment
granular-infer run       # dependency inference
granular-eval run        # held-out F1 + report

# 5. Serve
uvicorn granular.api.main:app --reload --port 8000   # API
cd apps/web && npm install && npm run dev             # frontend, http://localhost:3000
```

See [`INFRASTRUCTURE.md`](INFRASTRUCTURE.md) for the full environment-variable
reference and troubleshooting; see
[`SYSTEM_OVERVIEW.md`](SYSTEM_OVERVIEW.md#evaluation-system) for what
`granular-eval`'s five subcommands actually do and don't do today.

## Development

```bash
hatch run test        # pytest
hatch run typecheck   # mypy src/granular
hatch run lint        # ruff check
hatch run fmt         # ruff format
```

Frontend: `cd apps/web && npm run build` (typechecks and builds).

## Package layout

```text
src/granular/
  schema/       canonical types: Course, Programme, DeclaredEdge, InferredEdge, Concept, KnowledgeUnit
  ingestion/    catalogue adapters (Acalog/Purdue, purdue.io, UIUC) — parse only, no inference
  extraction/   concept extraction + 4-stage CS2023 alignment pipeline
  inference/    structural dependency inference -> DEPENDS_ON edges
  api/          FastAPI app: query resolution, discover + advisory-query services
  evaluation/   the evaluation harness (granular-eval)
apps/web/       Next.js + TypeScript frontend
```
