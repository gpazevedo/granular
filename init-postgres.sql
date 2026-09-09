-- Initialize PostgreSQL for Granular
-- Note: pgvector support can be added later with Docker volume pgvector installation

-- Create metadata table for tracking extraction runs
CREATE TABLE IF NOT EXISTS extraction_metadata (
    run_id VARCHAR(255) PRIMARY KEY,
    run_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    courses_processed INTEGER,
    concepts_extracted INTEGER,
    status VARCHAR(50)
);

-- Create embeddings table (without vector type for now)
-- This will store concept embeddings as JSONB until pgvector is added
CREATE TABLE IF NOT EXISTS concept_embeddings (
    id SERIAL PRIMARY KEY,
    concept_id VARCHAR(255) UNIQUE NOT NULL,
    concept_name TEXT NOT NULL,
    embedding_json JSONB,  -- Store as JSON until pgvector is available
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS concept_embeddings_id_idx 
ON concept_embeddings(concept_id);
