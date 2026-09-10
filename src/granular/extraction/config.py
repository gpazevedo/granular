"""ExtractionConfig — runtime configuration for the concept-extraction pipeline."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ExtractionConfig:
    vocabulary_path: Path = Path("data/cs2023_vocabulary.json")
    llm_model_id: str = "openai/gpt-4o-mini"
    embedding_model_id: str = "openai/text-embedding-3-small"
    top_k: int = 10
    min_confidence: float = 0.3
    # When set, the winning concept->KU alignment is verified by this chat model
    # before acceptance, rejecting embedding false positives (e.g. "solar car
    # economics" -> Requirements Engineering). Empty disables verification.
    alignment_verify_model_id: str = "openai/gpt-4o-mini"
    low_confidence_threshold: float = 0.5
    min_description_length: int = 20
    pgvector_dsn: str = "postgresql://granular:changeme@localhost:5432/granular"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"
    output_dir: Path = Path("data/extraction/output")
    summary_path: Path = Path("data/extraction/output/summary.json")
    adapter_name: str = "granular-extraction"
    adapter_version: str = "1.0.0"
    # Reranking signal weights
    weight_similarity: float = 0.40
    weight_cooccurrence: float = 0.35
    weight_level_proximity: float = 0.20
    weight_department_prior: float = 0.05
    # Verify-stage confidence: temperature for the softmax over the top-two
    # rerank scores (winner vs strongest rival). Lower = sharper (a small gap
    # already yields high confidence); higher = flatter. Rerank-score gaps are
    # small (~0.02–0.10), so a small temperature is needed for useful spread.
    confidence_temperature: float = 0.10

    def __post_init__(self) -> None:
        self.vocabulary_path = Path(self.vocabulary_path)
        self.output_dir = Path(self.output_dir)
        self.summary_path = Path(self.summary_path)
        if not (0.0 < self.min_confidence < 1.0):
            raise ValueError("min_confidence must be in (0, 1)")
        if self.top_k < 1:
            raise ValueError("top_k must be >= 1")

    @classmethod
    def from_toml(cls, path: Path) -> "ExtractionConfig":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(**{k: v for k, v in data.get("extraction", data).items()})

    @classmethod
    def from_env(cls, base: Optional["ExtractionConfig"] = None) -> "ExtractionConfig":
        cfg = base or cls()
        env_map = {
            "GRANULAR_VOCABULARY_PATH": ("vocabulary_path", Path),
            "GRANULAR_LLM_MODEL_ID": "llm_model_id",
            "GRANULAR_EMBEDDING_MODEL_ID": "embedding_model_id",
            "GRANULAR_TOP_K": ("top_k", int),
            "OPENAI_LLM_MODEL": "llm_model_id",
            "OPENAI_EMBEDDING_MODEL": "embedding_model_id",
            "ANTHROPIC_LLM_MODEL": "llm_model_id",  # Override with Anthropic if set
            "PGVECTOR_DSN": "pgvector_dsn",
            "NEO4J_URI": "neo4j_uri",
            "NEO4J_USER": "neo4j_user",
            "NEO4J_PASSWORD": "neo4j_password",
        }
        for env_key, field_spec in env_map.items():
            val = os.environ.get(env_key)
            if val is None:
                continue
            if isinstance(field_spec, tuple):
                fname, coerce = field_spec
                setattr(cfg, fname, coerce(val))
            else:
                setattr(cfg, field_spec, val)
        
        # If Anthropic model is set, wrap it with provider prefix
        if os.environ.get("ANTHROPIC_LLM_MODEL"):
            cfg.llm_model_id = f"anthropic/{os.environ['ANTHROPIC_LLM_MODEL']}"
        
        # If Bedrock model is set, wrap it with provider prefix
        if os.environ.get("BEDROCK_LLM_MODEL"):
            cfg.llm_model_id = f"bedrock/{os.environ['BEDROCK_LLM_MODEL']}"
        
        # Ensure embedding model has provider prefix
        if cfg.embedding_model_id and "/" not in cfg.embedding_model_id:
            cfg.embedding_model_id = f"openai/{cfg.embedding_model_id}"

        # Alignment verification model: explicit override, else follow the
        # extraction LLM so the provider (OpenAI/Anthropic/Bedrock) stays consistent.
        verify_override = os.environ.get("ALIGNMENT_VERIFY_MODEL")
        if verify_override is not None:
            cfg.alignment_verify_model_id = verify_override
        elif any(
            os.environ.get(k)
            for k in ("ANTHROPIC_LLM_MODEL", "BEDROCK_LLM_MODEL", "OPENAI_LLM_MODEL")
        ):
            cfg.alignment_verify_model_id = cfg.llm_model_id

        return cfg
