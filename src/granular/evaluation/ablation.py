"""AblationRunner — reruns inference under restricted conditions. (Task 9)"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from granular.evaluation.config import EvalConfig
from granular.evaluation.metric import InferredGraph, MetricCalculator, MetricResult
from granular.evaluation.split import Split
from granular.inference.config import PipelineMode

logger = logging.getLogger(__name__)


@dataclass
class AblationReport:
    retrieval_only: MetricResult
    retrieval_rerank: MetricResult
    full_pipeline: MetricResult


class AblationRunner:
    """Runs the metric under three ablation conditions against one held-out split.

    The inference rerun under each mode is provided as a callable so the runner
    can be tested without a live pipeline. The callable returns an InferredGraph.
    """

    def __init__(
        self,
        config: EvalConfig,
        infer_fn: Callable[[PipelineMode], InferredGraph],
    ) -> None:
        self._config = config
        self._infer_fn = infer_fn
        self._metric = MetricCalculator()

    def run_condition(
        self,
        mode: PipelineMode,
        held_out: list[tuple[str, str]],
        all_declared: set[tuple[str, str]],
    ) -> MetricResult:
        graph = self._infer_fn(mode)
        return self._metric.compute(held_out, graph, all_declared, None)

    def run_all(
        self,
        held_out: list[tuple[str, str]],
        all_declared: set[tuple[str, str]],
    ) -> AblationReport:
        return AblationReport(
            retrieval_only=self.run_condition(
                PipelineMode.RETRIEVAL_ONLY, held_out, all_declared
            ),
            retrieval_rerank=self.run_condition(
                PipelineMode.RETRIEVAL_RERANK, held_out, all_declared
            ),
            full_pipeline=self.run_condition(
                PipelineMode.FULL_PIPELINE, held_out, all_declared
            ),
        )
