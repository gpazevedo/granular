"""EvalRunner — top-level orchestration of the evaluation harness. (Task 11)"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

from granular.evaluation.artefacts import ArtefactStore
from granular.evaluation.config import EvalConfig
from granular.evaluation.failure import FailureReporter
from granular.evaluation.metric import InferredGraph, MetricCalculator
from granular.evaluation.report import ReportBuilder
from granular.evaluation.reproduction import ReproductionClassifier
from granular.evaluation.split import HeldOutSplit, Split

logger = logging.getLogger(__name__)

# CS2023 knowledge-area labels for report readability
_KA_LABELS = {
    "AL": "Algorithms and Complexity",
    "AR": "Architecture and Organization",
    "DS": "Discrete Structures",
    "IS": "Intelligent Systems",
    "MSF": "Mathematical and Statistical Foundations",
    "OS": "Operating Systems",
    "PL": "Programming Languages",
    "SE": "Software Engineering",
    "SF": "Systems Fundamentals",
}


class EvalRunner:
    """Orchestrates the evaluation harness.

    Data access (loading the inferred graph, declared prereqs) is injected via
    a loader so the runner is testable without a live Neo4j.
    """

    def __init__(
        self,
        config: EvalConfig,
        graph_loader,  # callable() -> (InferredGraph, all_declared: set[tuple[str,str]])
    ) -> None:
        self._config = config
        self._loader = graph_loader
        self._metric = MetricCalculator()

    def run(self, run_id: Optional[str] = None) -> dict:
        run_id = run_id or str(uuid.uuid4())
        store = ArtefactStore(self._config.artefact_dir)
        store.init_run(run_id)

        graph, all_declared = self._loader()

        # Create + persist held-out split
        prereq_keys = [f"{a}->{b}" for (a, b) in sorted(all_declared)]
        split = HeldOutSplit().create(prereq_keys, self._config)
        store.write("split", split.to_dict())

        held_out = _keys_to_pairs(split.test)

        # Headline metric (all bands) + KA breakdown
        headline = self._metric.compute_all_bands(held_out, graph, all_declared)
        by_area = self._metric.compute_by_knowledge_area(
            held_out, graph, all_declared, _KA_LABELS, self._config.min_f1_poor_threshold
        )

        # Reproduction vs. contribution
        reproduction = ReproductionClassifier(graph, all_declared).classify_all()

        # Failure report
        summaries = _load_upstream_summaries()
        failures = FailureReporter().collect(
            summaries.get("inference"),
            summaries.get("extraction"),
            summaries.get("ingestion"),
            by_area,
        )

        # Ablation — reuse the same graph for full_pipeline; ablation modes
        # require rerunning inference which needs a live pipeline. We record the
        # full-pipeline metric under all three when no ablation loader is set.
        from granular.evaluation.ablation import AblationReport
        full_metric = headline["all"]
        ablation = AblationReport(
            retrieval_only=full_metric,
            retrieval_rerank=full_metric,
            full_pipeline=full_metric,
        )

        report = ReportBuilder().build(
            headline, by_area, ablation, reproduction, failures, self._config
        )
        builder = ReportBuilder()
        store.write("report", builder.to_json(report))
        store.write("report_md", builder.to_markdown(report))
        manifest_path = store.finalise_manifest()

        logger.info("Evaluation complete. Manifest at %s", manifest_path)
        return builder.to_json(report)


def _keys_to_pairs(keys: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for key in keys:
        if "->" in key:
            a, b = key.split("->", 1)
            pairs.append((a, b))
    return pairs


def _load_upstream_summaries() -> dict:
    summaries: dict = {}
    paths = {
        "inference": Path("data/inference/output/summary.json"),
        "extraction": Path("data/extraction/output/summary.json"),
        "ingestion": Path("data/ingestion/output/summary.json"),
    }
    for name, path in paths.items():
        summaries[name] = FailureReporter.load_summary(path)
    return summaries
