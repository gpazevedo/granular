"""Discover-relevance evaluation.

Measures how well the query resolver maps plain-English student interests to the
right CS2023 knowledge areas. For each labelled query we resolve it, map the
resolved knowledge units to their areas, and compare against the expected areas.

Areas (not specific KU ids) are the unit of comparison because they are stable
across vocabulary revisions and are the meaningful notion of "did we understand
the query". Reports per-query and aggregate precision / recall / F1.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass
class QueryLabel:
    query: str
    expected_areas: set[str]


@dataclass
class QueryResult:
    query: str
    expected_areas: set[str]
    resolved_areas: set[str]

    @property
    def true_positives(self) -> int:
        return len(self.expected_areas & self.resolved_areas)

    @property
    def precision(self) -> float:
        return self.true_positives / len(self.resolved_areas) if self.resolved_areas else 0.0

    @property
    def recall(self) -> float:
        return self.true_positives / len(self.expected_areas) if self.expected_areas else 0.0


@dataclass
class DiscoverEvalReport:
    per_query: list[QueryResult] = field(default_factory=list)

    @property
    def macro_precision(self) -> float:
        return _mean([q.precision for q in self.per_query])

    @property
    def macro_recall(self) -> float:
        return _mean([q.recall for q in self.per_query])

    @property
    def macro_f1(self) -> float:
        p, r = self.macro_precision, self.macro_recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "macro_precision": round(self.macro_precision, 4),
            "macro_recall": round(self.macro_recall, 4),
            "macro_f1": round(self.macro_f1, 4),
            "query_count": len(self.per_query),
            "per_query": [
                {
                    "query": q.query,
                    "expected_areas": sorted(q.expected_areas),
                    "resolved_areas": sorted(q.resolved_areas),
                    "precision": round(q.precision, 4),
                    "recall": round(q.recall, 4),
                }
                for q in self.per_query
            ],
        }


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


class ResolverProtocol(Protocol):
    def resolve(self, query: str): ...


def load_labels(path: Path) -> list[QueryLabel]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        QueryLabel(query=q["query"], expected_areas=set(q["expected_areas"]))
        for q in data.get("queries", [])
    ]


def evaluate_discover_relevance(
    labels: list[QueryLabel],
    resolver: ResolverProtocol,
    ku_to_area: dict[str, str],
) -> DiscoverEvalReport:
    """Resolve each labelled query and score resolved-area precision/recall.

    `ku_to_area` maps ku_id -> knowledge-area code, used to translate the
    resolver's resolved ku_ids into areas for comparison.
    """
    results: list[QueryResult] = []
    for label in labels:
        resolution = resolver.resolve(label.query)
        resolved_areas = {
            ku_to_area[k] for k in resolution.ku_ids if k in ku_to_area
        }
        results.append(
            QueryResult(
                query=label.query,
                expected_areas=label.expected_areas,
                resolved_areas=resolved_areas,
            )
        )
    return DiscoverEvalReport(per_query=results)
