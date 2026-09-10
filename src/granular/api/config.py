"""APIConfig — runtime configuration for the advisory query backend."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class APIConfig:
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"
    pgvector_dsn: str = "postgresql://granular:changeme@localhost:5432/granular"
    embedding_model_id: str = "openai/text-embedding-3-small"
    # A capable chat model used to interpret the student's query and select,
    # from the embedding-retrieved candidates, the knowledge units that
    # genuinely match their intent. Set to "" to disable LLM reranking and fall
    # back to embedding-only resolution.
    resolution_llm_model_id: str = "openai/gpt-4o"
    frontend_origin: str = "http://localhost:3000"
    min_coverage_courses: int = 1
    max_combinations: int = 5
    max_combination_size: int = 3
    resolution_min_score: float = 0.3
    resolution_top_k: int = 15
    entitlement_patterns: list[str] = field(
        default_factory=lambda: [
            r"\bexempt\b",
            r"\byou (?:will|can|should) master\b",
            r"\bcovers everything\b",
            r"\ball you need\b",
            r"\bfully prepares?\b",
            r"\byou can skip\b",
        ]
    )

    @classmethod
    def from_env(cls) -> "APIConfig":
        cfg = cls()
        cfg.neo4j_uri = os.environ.get("NEO4J_URI", cfg.neo4j_uri)
        cfg.neo4j_user = os.environ.get("NEO4J_USER", cfg.neo4j_user)
        cfg.neo4j_password = os.environ.get("NEO4J_PASSWORD", cfg.neo4j_password)
        cfg.pgvector_dsn = os.environ.get("PGVECTOR_DSN", cfg.pgvector_dsn)
        cfg.embedding_model_id = os.environ.get("OPENAI_EMBEDDING_MODEL", cfg.embedding_model_id)
        cfg.frontend_origin = os.environ.get("FRONTEND_ORIGIN", cfg.frontend_origin)
        # Optional override for the query-resolution chat model.
        cfg.resolution_llm_model_id = os.environ.get(
            "RESOLUTION_LLM_MODEL", cfg.resolution_llm_model_id
        )
        return cfg
