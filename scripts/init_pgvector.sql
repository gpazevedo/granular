CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS embeddings (
    id          TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,      -- 'concept' or 'knowledge_unit'
    label       TEXT NOT NULL,
    vector      vector(1536),
    model_id    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS embeddings_vector_idx
    ON embeddings USING ivfflat (vector vector_cosine_ops)
    WITH (lists = 100);
