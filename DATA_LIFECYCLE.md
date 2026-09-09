# Data Lifecycle & Persistence

## Storage Model

All data in Granular is **persisted in Docker volumes** that survive container restarts and rebuilds.

### Volumes

| Volume | Service | Purpose | Persistence |
|---|---|---|---|
| `granular_neo4j-data` | Neo4j | Graph store (concepts, relationships, alignments) | ✅ Persistent |
| `granular_neo4j-logs` | Neo4j | Transaction logs | ✅ Persistent |
| `granular_postgres-data` | PostgreSQL | Metadata, embeddings | ✅ Persistent |

### Workflow

```
1. INGESTION (one-time)
   ↓ Reads: data/ingestion/uiuc/courses.jsonl (from UIUC catalogue)
   ↓ Writes: PostgreSQL metadata table
   ✓ No graph data yet

2. EXTRACTION (one-time per iteration)
   ↓ Reads: PostgreSQL metadata
   ↓ Calls: AWS Bedrock (Nova) for concept extraction
   ↓ Writes: Neo4j (concepts, course→concept edges)
   ✓ Persisted in neo4j-data volume

3. INFERENCE (one-time per iteration)
   ↓ Reads: Neo4j (all concepts, prerequisites)
   ↓ Computes: Structural dependencies, ordering
   ↓ Writes: Neo4j (inferred edges)
   ✓ Persisted in neo4j-data volume

4. EVALUATION (repeatable)
   ↓ Reads: Neo4j (all data)
   ↓ Computes: F1, ablations, regressions
   ↓ Writes: data/evaluation/output/

5. ADVISORY QUERIES (repeatable)
   ↓ Reads: Neo4j + PostgreSQL
   ↓ Responds: FastAPI discover endpoint
   ✓ No writes to persistent storage
```

## Data Retention

### Persistent (survives `docker compose stop` and `docker compose down`)

- **Neo4j database** (`neo4j-data` volume)
  - All concepts extracted from courses
  - All declared prerequisites from course descriptions
  - All inferred structural relationships
  - Survives: service restarts, container recreations, even `docker compose down`

- **PostgreSQL** (`postgres-data` volume)
  - Concept embeddings (via OpenAI text-embedding-3-small)
  - Metadata (extraction run records, etc.)

- **File system**
  - `data/ingestion/uiuc/` — ingestion output (courses.jsonl)
  - `.env` — your configuration

### Ephemeral (lost if volume is deleted)

- All Neo4j and PostgreSQL data is *only* safe while volumes exist
- `docker compose down -v` **deletes all volumes** — this is destructive

## Workflow Best Practices

### Safe workflow

```bash
# 1. Start services (persistent volumes auto-created on first run)
docker compose up -d

# 2. Run ingestion (one-time)
granular-ingest uiuc --output-dir data/ingestion/uiuc

# 3. Run extraction (one-time; writes to Neo4j)
granular-extract run

# 4. Run inference (one-time; writes to Neo4j)
granular-infer run

# 5. Stop services (data persists in volumes)
docker compose stop

# ... hours/days later ...

# 6. Restart services — all data is still there
docker compose start

# 7. Run evaluation (repeatable; only reads)
granular-eval run

# 8. Start API (repeatable; only reads)
uvicorn granular.api.main:app --reload
```

### Destructive operations

**WARNING: These operations delete all data permanently:**

```bash
# Delete volumes AND data (caution!)
docker compose down -v

# Delete specific volume (if you know what you're doing)
docker volume rm granular_neo4j-data
```

## Re-running stages without losing data

If you want to **re-run extraction or inference** without re-ingesting:

```bash
# Extraction reads from data/ingestion/uiuc/ (file system, not neo4j)
# Safe to re-run: just clears and re-populates neo4j-data
granular-extract run

# Same for inference
granular-infer run
```

The ingestion output (`data/ingestion/uiuc/courses.jsonl`) is the **authoritative source**. Extraction and inference always read from it, so you can safely re-run those stages.

## Inspecting persisted data

### Check Neo4j data

```bash
docker exec granular-neo4j cypher-shell -u neo4j -p granular-password \
  "MATCH (c:Concept) RETURN COUNT(c) as concept_count;"
```

### Check PostgreSQL data

```bash
docker exec granular-postgres psql -U granular -d granular \
  "SELECT COUNT(*) FROM concept_embeddings;"
```

### Verify volume contents

```bash
# Show volumes and their size
docker volume ls --format "table {{.Name}}\t{{.Size}}"

# Or inspect a specific volume
docker volume inspect granular_neo4j-data
```

## Backup & Recovery

### Manual backup (one-time snapshot)

```bash
# Backup Neo4j database
docker exec granular-neo4j neo4j-admin database backup \
  --to-path /data/backup full 2>/dev/null

# Copy from container to host
docker cp granular-neo4j:/data/backup ./neo4j-backup

# Backup PostgreSQL
docker exec granular-postgres pg_dump -U granular granular \
  > postgres-backup.sql
```

### Restore from backup

```bash
# Restore PostgreSQL
docker exec -i granular-postgres psql -U granular granular < postgres-backup.sql

# Note: Neo4j backup restore is more complex; use official docs if needed
```

## Summary

✅ **Your data is safe.** Both Neo4j and PostgreSQL use persistent Docker volumes.  
✅ **Safe to stop/restart.** All data survives `docker compose stop`.  
✅ **Ingestion is truly one-time.** Output lives in `data/ingestion/uiuc/` (file system).  
⚠️ **Only delete with `docker compose down -v` if you want to start fresh.**

The pipeline stages (extract → infer → eval) read from persisted data and are safe to re-run.
