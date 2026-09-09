"""EvalConfig — runtime configuration for the evaluation harness. (Task 1)"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class EvalConfig:
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"
    held_out_fraction: float = 0.20
    random_seed: int = 42
    min_f1_poor_threshold: float = 0.40
    confidence_high: float = 0.70
    confidence_medium_low: float = 0.40
    distractor_ratio: float = 1.0
    institution: str = "Purdue University"
    discipline: str = "Computer Science"
    catalogue_year: str = "2026-2027"
    ingestion_run_id: str = "unknown"
    output_dir: Path = Path("data/evaluation/output")
    artefact_dir: Path = Path("data/evaluation/runs")

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        self.artefact_dir = Path(self.artefact_dir)
        if not (0.0 < self.held_out_fraction < 1.0):
            raise ValueError("held_out_fraction must be in (0, 1)")
        if self.random_seed < 0:
            raise ValueError("random_seed must be non-negative")
        if self.confidence_high <= self.confidence_medium_low:
            raise ValueError("confidence_high must be > confidence_medium_low")

    @classmethod
    def from_toml(cls, path: Path) -> "EvalConfig":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(**{k: v for k, v in data.get("evaluation", data).items()})

    @classmethod
    def from_env(cls, base: Optional["EvalConfig"] = None) -> "EvalConfig":
        cfg = base or cls()
        env_map = {
            "NEO4J_URI": "neo4j_uri",
            "NEO4J_USER": "neo4j_user",
            "NEO4J_PASSWORD": "neo4j_password",
            "GRANULAR_HELD_OUT_FRACTION": ("held_out_fraction", float),
            "GRANULAR_RANDOM_SEED": ("random_seed", int),
            "GRANULAR_CATALOGUE_YEAR": "catalogue_year",
            "GRANULAR_INGESTION_RUN_ID": "ingestion_run_id",
        }
        for env_key, spec in env_map.items():
            val = os.environ.get(env_key)
            if val is None:
                continue
            if isinstance(spec, tuple):
                fname, coerce = spec
                setattr(cfg, fname, coerce(val))
            else:
                setattr(cfg, spec, val)
        return cfg

    def confidence_band(self, confidence: float) -> str:
        if confidence >= self.confidence_high:
            return "high"
        if confidence >= self.confidence_medium_low:
            return "medium"
        return "low"
