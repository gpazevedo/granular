"""ExtractionSummary — structured run summary for the extraction pipeline."""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import uuid


@dataclass
class ExtractionSummary:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    completed_at: Optional[datetime] = None
    courses_processed: int = 0
    concepts_extracted: int = 0
    concepts_aligned: int = 0
    concepts_unaligned: int = 0
    concepts_low_confidence: int = 0
    concepts_skipped_empty: int = 0
    confidence_mean: float = 0.0
    confidence_median: float = 0.0
    confidence_p10: float = 0.0
    confidence_p90: float = 0.0
    duration_seconds: float = 0.0

    def compute_confidence_stats(self, confidences: list[float]) -> None:
        if not confidences:
            return
        ordered = sorted(confidences)
        self.confidence_mean = statistics.mean(ordered)
        self.confidence_median = statistics.median(ordered)
        self.confidence_p10 = ordered[max(0, int(len(ordered) * 0.10) - 1)]
        self.confidence_p90 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.90))]

    def finish(self) -> None:
        self.completed_at = datetime.now(tz=timezone.utc)
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        def _default(obj: object) -> object:
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Not serialisable: {type(obj)}")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, default=_default)
