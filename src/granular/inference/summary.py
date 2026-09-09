"""InferenceSummary — structured run summary for the inference pipeline."""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import uuid


@dataclass
class KACoverageRow:
    knowledge_area: str
    concept_count: int
    dependency_edge_count: int
    similarity_edge_count: int
    mean_confidence: float


@dataclass
class InferenceSummary:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    completed_at: Optional[datetime] = None
    concepts_processed: int = 0
    dependency_edges_inferred: int = 0
    similarity_edges_inferred: int = 0
    edges_rejected_cycle: int = 0
    edges_rejected_ordering: int = 0
    edges_below_min_score: int = 0
    low_confidence_similarity: int = 0
    confidence_mean: float = 0.0
    confidence_median: float = 0.0
    confidence_p10: float = 0.0
    confidence_p90: float = 0.0
    knowledge_area_coverage: list[KACoverageRow] = field(default_factory=list)
    duration_seconds: float = 0.0

    def compute_confidence_stats(self, confidences: list[float]) -> None:
        if not confidences:
            return
        ordered = sorted(confidences)
        self.confidence_mean = statistics.mean(ordered)
        self.confidence_median = statistics.median(ordered)
        self.confidence_p10 = ordered[max(0, int(len(ordered) * 0.10) - 1)]
        self.confidence_p90 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.90))]

    def total_candidates(self) -> int:
        return (
            self.dependency_edges_inferred
            + self.edges_rejected_cycle
            + self.edges_rejected_ordering
        )

    def rejection_rate(self) -> float:
        total = self.total_candidates()
        if total == 0:
            return 0.0
        rejected = self.edges_rejected_cycle + self.edges_rejected_ordering
        return rejected / total * 100

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
