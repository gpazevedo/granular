"""InferenceConfig — runtime configuration for the concept-graph-inference pipeline."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class PipelineMode(str, Enum):
    """Ablation modes for the inference pipeline."""

    RETRIEVAL_ONLY = "retrieval_only"
    RETRIEVAL_RERANK = "retrieval_rerank"
    FULL_PIPELINE = "full_pipeline"


@dataclass
class SignalWeights:
    course_level: float = 0.45
    prerequisite_prior: float = 0.40
    ku_cooccurrence: float = 0.15


@dataclass
class InferenceConfig:
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"
    confidence_high: float = 0.70
    confidence_medium_low: float = 0.40
    min_dependency_score: float = 0.35
    rejection_threshold_pct: float = 20.0
    model_id: str = "granular-inference/1.0.0"
    adapter_name: str = "granular-inference"
    adapter_version: str = "1.0.0"
    output_dir: Path = Path("data/inference/output")
    summary_path: Path = Path("data/inference/output/summary.json")
    signal_weights: SignalWeights = field(default_factory=SignalWeights)
    mode: PipelineMode = PipelineMode.FULL_PIPELINE

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        self.summary_path = Path(self.summary_path)
        if self.confidence_high <= self.confidence_medium_low:
            raise ValueError("confidence_high must be > confidence_medium_low")
        if not (0.0 <= self.min_dependency_score <= 1.0):
            raise ValueError("min_dependency_score must be in [0, 1]")

    @classmethod
    def from_toml(cls, path: Path) -> "InferenceConfig":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        section = data.get("inference", data)
        weights = section.pop("signal_weights", {})
        cfg = cls(**section)
        if weights:
            cfg.signal_weights = SignalWeights(**weights)
        return cfg

    @classmethod
    def from_env(cls, base: Optional["InferenceConfig"] = None) -> "InferenceConfig":
        cfg = base or cls()
        env_map = {
            "NEO4J_URI": "neo4j_uri",
            "NEO4J_USER": "neo4j_user",
            "NEO4J_PASSWORD": "neo4j_password",
        }
        for env_key, fname in env_map.items():
            val = os.environ.get(env_key)
            if val is not None:
                setattr(cfg, fname, val)
        return cfg

    def confidence_band(self, confidence: float) -> str:
        if confidence >= self.confidence_high:
            return "high"
        if confidence >= self.confidence_medium_low:
            return "medium"
        return "low"
