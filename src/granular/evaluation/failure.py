"""FailureReporter — first-class failure counts. (Task 7)"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from granular.evaluation.metric import KAMetricResult


@dataclass
class FailureReport:
    not_machine_checkable_rules: int = 0
    model_outputs_rejected: int = 0
    edges_removed_cycle_prevention: int = 0
    edges_rejected_ordering: int = 0
    poor_coverage_areas: list[str] = field(default_factory=list)


class FailureReporter:
    """Aggregates failure counts from upstream pipeline summaries.

    All integer fields are always present (default 0), never None or absent.
    """

    def collect(
        self,
        inference_summary: Optional[dict],
        extraction_summary: Optional[dict],
        ingestion_summary: Optional[dict],
        ka_results: list[KAMetricResult],
    ) -> FailureReport:
        report = FailureReport()

        if ingestion_summary:
            report.not_machine_checkable_rules = int(
                ingestion_summary.get("prereqs_unstructured", 0)
            )

        if extraction_summary:
            # Model outputs rejected ≈ unaligned + low-confidence
            report.model_outputs_rejected = int(
                extraction_summary.get("concepts_unaligned", 0)
            ) + int(extraction_summary.get("concepts_low_confidence", 0))

        if inference_summary:
            report.edges_removed_cycle_prevention = int(
                inference_summary.get("edges_rejected_cycle", 0)
            )
            report.edges_rejected_ordering = int(
                inference_summary.get("edges_rejected_ordering", 0)
            )

        report.poor_coverage_areas = [
            r.knowledge_area_label for r in ka_results if r.poor_coverage
        ]
        return report

    @staticmethod
    def load_summary(path: Path) -> Optional[dict]:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
