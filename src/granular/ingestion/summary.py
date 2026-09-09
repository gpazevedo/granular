"""IngestSummary — structured run summary written to JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import uuid


@dataclass
class FailureRecord:
    url: str
    reason: str
    status_code: Optional[int] = None


@dataclass
class SkipRecord:
    url: str
    reason: str  # e.g. "robots_disallowed", "dry_run"


@dataclass
class IngestSummary:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    completed_at: Optional[datetime] = None
    courses_attempted: int = 0
    courses_succeeded: int = 0
    courses_failed: list[FailureRecord] = field(default_factory=list)
    courses_skipped: list[SkipRecord] = field(default_factory=list)
    programmes_ingested: int = 0
    prereqs_structured: int = 0
    prereqs_unstructured: int = 0
    odata_fallback_used: bool = False
    odata_discrepancies: int = 0
    duration_seconds: float = 0.0

    def finish(self) -> None:
        self.completed_at = datetime.now(tz=timezone.utc)
        delta = self.completed_at - self.started_at
        self.duration_seconds = delta.total_seconds()

    def failure_rate(self) -> float:
        if self.courses_attempted == 0:
            return 0.0
        return len(self.courses_failed) / self.courses_attempted * 100

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        def _default(obj: object) -> object:
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Not serialisable: {type(obj)}")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, default=_default)
