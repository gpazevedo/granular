# Infrastructure Setup

This document explains how to set up the local development environment for running the Granular pipeline end-to-end.

## Requirements

- Docker & Docker Compose (for Neo4j and PostgreSQL/pgvector)
- Python 3.12+ (installed; `.venv` already configured)
- OpenAI API key (for LLM concept extraction)

## Quick Start

### 1. Start services

```bash
docker compose up -d
```

This starts:
- **Neo4j** (bolt://localhost:7687) — graph store for the concept knowledge graph
- **PostgreSQL with pgvector** (localhost:5432) — vector store for embeddings

Both services write to Docker volumes, so data persists across restarts. See `DATA_LIFECYCLE.md` for details.

### 2. Configure .env

Copy `.env.example` to `.env` and fill in your OpenAI API key:

```bash
cp .env.example .env
# Edit .env and replace sk-... with your actual OpenAI key
```

The database credentials (`granular-password`) are pre-configured to match Docker Compose.

### 3. Initialize databases

The services auto-initialize on first start. You can verify connectivity:

**Neo4j** (Cypher shell):
```bash
docker exec -it granular-neo4j cypher-shell -u neo4j -p granular-password "RETURN 'Neo4j ready'"
```

**PostgreSQL** (psql):
```bash
docker exec -it granular-postgres psql -U granular -d granular -c "SELECT version();"
```

Or access the Neo4j Browser at http://localhost:7474 (username: `neo4j`, password: `granular-password`).

## Pipeline Execution

Once infrastructure is up and .env is configured:

### Ingest courses

```bash
granular-ingest uiuc --output-dir data/ingestion/uiuc
```

Reads the UIUC static catalog and writes 94 CS courses to `data/ingestion/uiuc/`. Done once per institution.

### Extract concepts

```bash
granular-extract run
```

Reads courses from the ingestion output, calls the LLM to extract CS2023-aligned concepts, and writes:
- Concept records to the graph store (Neo4j)
- Alignment edges (course → concept)
- Embeddings to the vector store (pgvector)

Supports OpenAI, Anthropic Claude, or AWS Bedrock (Nova). Configure in `.env`:

**AWS Bedrock Nova (recommended for cost):**
```bash
BEDROCK_LLM_MODEL=us.amazon.nova-lite-v1:0
OPENAI_API_KEY=sk-...  # For embeddings
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
AWS_REGION=us-east-1
```

Requires AWS credentials (`~/.aws/credentials` or env vars).

**Anthropic Claude:**
```bash
ANTHROPIC_LLM_MODEL=claude-3-5-haiku-20241022
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...  # For embeddings
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

**OpenAI (default):**
```bash
OPENAI_LLM_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_API_KEY=sk-...
```

### Infer graph structure

```bash
granular-infer run
```

Reads the extracted concepts and declared prerequisites, runs structural inference (course level, co-occurrence, ordering), and writes inferred edges.

### Evaluate

```bash
granular-eval run
```

Computes held-out prerequisite F1, ablation metrics, and regression tests against the inferred graph.

### Run advisory queries

```bash
uvicorn granular.api.main:app --reload --port 8000
```

Starts the FastAPI discovery endpoint. In a separate terminal:

```bash
cd apps/web && npm run dev
```

Starts the Next.js frontend at http://localhost:3000.

## Environment Variables Reference

| Variable | Purpose | Example |
|---|---|---|
| `NEO4J_URI` | Bolt connection to Neo4j | `bolt://localhost:7687` |
| `NEO4J_USER` | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j password | `granular-password` |
| `PGVECTOR_DSN` | PostgreSQL connection string | `postgresql://granular:granular-password@localhost:5432/granular` |
| `OPENAI_API_KEY` | LLM API key | `sk-...` |
| `OPENAI_EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small` |
| `OPENAI_LLM_MODEL` | LLM model | `gpt-4o-mini` |
| `FRONTEND_ORIGIN` | CORS origin for frontend | `http://localhost:3000` |

## Stopping and Cleaning Up

**Stop services:**
```bash
docker compose down
```

**Stop + remove volumes (WARNING: deletes all data):**
```bash
docker compose down -v
```

**Restart services:**
```bash
docker compose restart
```

## Troubleshooting

### Neo4j won't start
Check logs:
```bash
docker compose logs neo4j
```

Ensure port 7687 is not in use. Change in `docker-compose.yml` if needed.

### PostgreSQL connection refused
Wait a few seconds for the service to initialize. Verify with:
```bash
docker compose ps
```

Both services should show `healthy` status.

### LLM calls failing
Verify your `OPENAI_API_KEY` is set and valid. Check the extraction logs for HTTP 401/403 errors.

## Network Access

Services are configured on the `granular-net` Docker network for inter-container communication. To connect from the host machine:
- Neo4j: `localhost:7687` (Bolt) or `localhost:7474` (Browser)
- PostgreSQL: `localhost:5432`

These ports are exposed in `docker-compose.yml`.
