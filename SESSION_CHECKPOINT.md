# Session Checkpoint — Ready for Extraction & Beyond

**Date:** September 9, 2026  
**Branch:** main  
**Status:** Infrastructure complete, ready to run concept extraction

## What's Done

### 1. **Data Pipeline** (6 packages, all on main)

- ✅ `granular.schema` — canonical data model with strict invariants
- ✅ `granular.ingestion` — UIUC static-catalog adapter (94 CS courses ingested)
- ✅ `granular.extraction` — concept extraction (LLM-based, supports OpenAI/Anthropic/Bedrock)
- ✅ `granular.inference` — structural graph inference (DAG guarantee, ordering)
- ✅ `granular.evaluation` — held-out F1, ablation, regression metrics
- ✅ `granular.api` — FastAPI advisory queries (discover endpoint)

### 2. **Frontend**

- ✅ `apps/web` — Next.js 14 discover UI (typechecks and builds clean)

### 3. **Infrastructure**

- ✅ Docker Compose (Neo4j + PostgreSQL running with persistent volumes)
- ✅ AWS Bedrock integration (Amazon Nova models supported)
- ✅ LLM abstraction layer (OpenAI, Anthropic, Bedrock all work)

### 4. **Data**

- ✅ 94 UIUC CS courses ingested to `data/ingestion/uiuc/courses.jsonl`
- ✅ 77 with usable descriptions (≥50 chars)
- ✅ 201 prerequisite edges extracted from prose descriptions

### 5. **Documentation**

- ✅ `INFRASTRUCTURE.md` — setup, services, env vars
- ✅ `DATA_LIFECYCLE.md` — persistence model, workflows, backups
- ✅ `docker-compose.yml` — persistent volumes for Neo4j and PostgreSQL
- ✅ `.env.example` — configuration template for all LLM providers

## What's Next

### Immediate Next Steps

**1. Set up .env and start extraction**

```bash
# Copy template
cp .env.example .env

# Option A: AWS Bedrock (recommended — charged to your AWS account)
# Edit .env:
#   BEDROCK_LLM_MODEL=us.amazon.nova-lite-v1:0
#   OPENAI_EMBEDDING_MODEL=text-embedding-3-small
#   OPENAI_API_KEY=sk-...  (for embeddings only)
#   AWS_REGION=us-east-1

# Option B: Anthropic Claude Haiku
# Edit .env:
#   ANTHROPIC_LLM_MODEL=claude-3-5-haiku-20241022
#   ANTHROPIC_API_KEY=sk-ant-...
#   OPENAI_API_KEY=sk-...  (for embeddings)
#   OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

**2. Verify services are running**

```bash
# Start services if not running
docker compose up -d

# Verify
docker compose ps  # Both neo4j and postgres should be healthy
```

**3. Run extraction (one-time)**

```bash
# Extract concepts from 94 UIUC courses using chosen LLM
# Reads: data/ingestion/uiuc/courses.jsonl
# Writes: Neo4j (concepts, edges) + PostgreSQL (embeddings)
granular-extract run

# Estimated time: 10-15 minutes (94 courses × 5-10 sec each)
# Estimated cost: ~$0.05-0.20 (depending on LLM)
```

**4. Run inference (one-time)**

```bash
# Build structural concept graph from extracted concepts + prerequisites
# Reads: Neo4j (all extracted data)
# Writes: Neo4j (inferred edges)
granular-infer run

# Time: < 1 minute
# Cost: $0 (local computation)
```

**5. Run evaluation (repeatable)**

```bash
# Compute held-out prerequisite F1, ablations, regressions
# Reads: Neo4j (all data)
# Writes: data/evaluation/output/
granular-eval run

# Time: < 1 minute
# Cost: $0 (local computation)
```

**6. Start advisory API**

```bash
# Terminal 1: Start backend
uvicorn granular.api.main:app --reload --port 8000

# Terminal 2: Start frontend
cd apps/web && npm run dev

# Open http://localhost:3000
# Discover courses by learning interests
```

## Key Files to Know

| File | Purpose |
| --- | --- |
| `data/ingestion/uiuc/courses.jsonl` | Ingestion output (94 courses, structured) |
| `.env` | Your configuration (LLM provider, API keys, AWS region) |
| `docker-compose.yml` | Service definitions (Neo4j, PostgreSQL) |
| `DATA_LIFECYCLE.md` | Persistence model, backup procedures |
| `INFRASTRUCTURE.md` | Setup guide, environment variables |
| `pyproject.toml` | Python dependencies (including boto3 for Bedrock) |

## Environment Setup Checklist

Before starting extraction, ensure:

- [ ] Docker Compose is installed (`docker compose version`)
- [ ] AWS credentials configured (if using Bedrock):
  - [ ] `~/.aws/credentials` or `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` env vars
  - [ ] AWS region set (default: `us-east-1` in `.env`)
- [ ] `.env` file created with chosen LLM provider configured
- [ ] Services running: `docker compose ps` shows neo4j and postgres as healthy
- [ ] Python packages installed: `.venv/bin/pip install -e .` (or from repo root)

## LLM Provider Quick Reference

| Provider | Setup | Cost (94 courses) | Notes |
| --- | --- | --- | --- |
| **AWS Bedrock Nova** | `BEDROCK_LLM_MODEL=us.amazon.nova-lite-v1:0` | ~$0.05 | Recommended: cheapest, AWS-native |
| **Anthropic Haiku** | `ANTHROPIC_LLM_MODEL=claude-3-5-haiku-20241022` | ~$0.15 | Good: fast, reliable |
| **OpenAI GPT-4o-mini** | `OPENAI_LLM_MODEL=gpt-4o-mini` | ~$0.30 | Expensive: good quality |

All require `OPENAI_EMBEDDING_MODEL=text-embedding-3-small` for embeddings (~$0.01 per 94 courses).

## Data Persistence

✅ **All data persists** — Neo4j and PostgreSQL use Docker volumes that survive restarts.

Safe workflow:

```bash
docker compose up -d        # Start (volumes auto-create)
granular-extract run        # Extract once (writes to persistent volume)
docker compose stop         # Stop (data stays in volumes)
# ... hours/days later ...
docker compose start        # Restart (all data intact)
granular-infer run          # Run inference (reads persisted extraction data)
```

⚠️ **Destructive:** `docker compose down -v` deletes volumes permanently.

See `DATA_LIFECYCLE.md` for full details.

## Testing Without LLM Calls

To verify the pipeline works before spending on LLM calls:

```bash
# Run extraction with a single course (no real LLM calls, mocked)
cd tests/extraction && python -m pytest test_extractor.py -v

# All 178 backend tests pass:
pytest tests/
```

## Troubleshooting

**Neo4j connection refused?**

```bash
docker compose logs neo4j | tail -20
docker compose restart neo4j
sleep 10
```

**PostgreSQL not healthy?**

```bash
docker compose logs postgres
docker compose restart postgres
```

**LLM API errors?**

- Check `.env` has correct credentials and model IDs
- Verify AWS region is set (if using Bedrock): `echo $AWS_REGION`
- Verify OpenAI key is set: `echo $OPENAI_API_KEY | head -c 10`

**Concept extraction slow or failing?**

- Extraction is rate-limited (1 req/sec per LLM to avoid throttling)
- Expected: ~10-15 minutes for 94 courses
- Check logs: `docker compose logs` or run with `-vv` flag

## Next Session Handoff

When handing to a fresh session, provide:

1. This file (`SESSION_CHECKPOINT.md`)
2. A `.env` file with configured LLM provider and credentials
3. Confirm Docker services are running: `docker compose ps`

Fresh session can then immediately:

```bash
granular-extract run  # Pick up where you left off
```

## Summary

**Current state:** Infrastructure ready, 94 courses ingested, persistent storage configured.

**Next action:** Configure `.env`, verify services, run `granular-extract run`.

**Timeline:** Extraction ~10-15 min, inference ~1 min, evaluation ~1 min, API startup instant.

**Cost:** ~$0.05-0.30 depending on LLM choice (mostly on extraction).

Good luck! 🚀
