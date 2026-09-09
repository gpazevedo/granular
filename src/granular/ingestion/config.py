"""IngestConfig — runtime configuration for the catalogue-ingestion pipeline."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional


@dataclass
class IngestConfig:
    catalogue_base_url: str = "https://catalog.purdue.edu"
    purdue_io_base_url: str = "https://api.purdue.io/odata"
    subject_filter: str = "CS"
    requests_per_second: float = 1.0
    output_dir: Path = Path("data/ingestion/output")
    summary_path: Path = Path("data/ingestion/output/summary.json")
    failure_threshold_pct: float = 10.0
    force_refetch: bool = False
    since_date: Optional[date] = None
    user_agent: str = "GranularResearchBot/1.0"
    adapter_name: str = "purdue_acalog"
    adapter_version: str = "1.0.0"
    cache_db_path: Path = Path("data/ingestion/fetch_cache.db")
    workers: int = 1

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        self.summary_path = Path(self.summary_path)
        self.cache_db_path = Path(self.cache_db_path)
        if self.requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        if self.failure_threshold_pct < 0 or self.failure_threshold_pct > 100:
            raise ValueError("failure_threshold_pct must be in [0, 100]")
        if self.workers < 1:
            raise ValueError("workers must be >= 1")

    @classmethod
    def from_toml(cls, path: Path) -> "IngestConfig":
        """Load config from a TOML file."""
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(**{k: v for k, v in data.get("ingestion", data).items()})

    @classmethod
    def from_env(cls, base: Optional["IngestConfig"] = None) -> "IngestConfig":
        """Override config fields from GRANULAR_* environment variables."""
        cfg = base or cls()
        env_map = {
            "GRANULAR_CATALOGUE_BASE_URL": "catalogue_base_url",
            "GRANULAR_PURDUE_IO_BASE_URL": "purdue_io_base_url",
            "GRANULAR_SUBJECT_FILTER": "subject_filter",
            "GRANULAR_REQUESTS_PER_SECOND": ("requests_per_second", float),
            "GRANULAR_OUTPUT_DIR": ("output_dir", Path),
            "GRANULAR_ADAPTER_NAME": "adapter_name",
            "GRANULAR_ADAPTER_VERSION": "adapter_version",
            "GRANULAR_WORKERS": ("workers", int),
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
        return cfg
