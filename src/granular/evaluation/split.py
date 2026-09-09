"""HeldOutSplit — reproducible train/test split of declared prerequisites. (Task 3)"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import floor
from pathlib import Path

from granular.evaluation.config import EvalConfig

logger = logging.getLogger(__name__)


@dataclass
class Split:
    train: list[str]  # edge_ids (or "course->prereq" keys)
    test: list[str]
    seed: int
    fraction: float
    ingestion_run_id: str
    created_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "train": self.train,
            "test": self.test,
            "seed": self.seed,
            "fraction": self.fraction,
            "ingestion_run_id": self.ingestion_run_id,
            "created_at": self.created_at,
        }


class HeldOutSplit:
    """Creates and persists a reproducible train/test split before inference runs."""

    def create(self, prereq_keys: list[str], config: EvalConfig) -> Split:
        """Create a split from declared prerequisite keys.

        prereq_keys: list of "course_id->prereq_course_id" identifiers.
        Uses a fixed seed for reproducibility.
        """
        shuffled = list(prereq_keys)
        random.Random(config.random_seed).shuffle(shuffled)
        n_test = floor(len(shuffled) * config.held_out_fraction)
        test = shuffled[len(shuffled) - n_test:] if n_test > 0 else []
        train = shuffled[: len(shuffled) - n_test]
        logger.info(
            "Split: %d train, %d test (seed=%d, fraction=%.2f)",
            len(train),
            len(test),
            config.random_seed,
            config.held_out_fraction,
        )
        return Split(
            train=train,
            test=test,
            seed=config.random_seed,
            fraction=config.held_out_fraction,
            ingestion_run_id=config.ingestion_run_id,
        )

    def load(self, path: Path) -> Split:
        """Load a split from a JSON file, validating required fields."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for required in ("train", "test", "seed", "fraction", "ingestion_run_id"):
            if required not in data:
                raise ValueError(f"Split file missing required field: {required}")
        return Split(
            train=data["train"],
            test=data["test"],
            seed=data["seed"],
            fraction=data["fraction"],
            ingestion_run_id=data["ingestion_run_id"],
            created_at=data.get("created_at", ""),
        )
