"""Tests for AblationRunner, ReportBuilder, and EvalRunner (Tasks 9, 10, 11)."""

from __future__ import annotations

from granular.evaluation.ablation import AblationRunner
from granular.evaluation.config import EvalConfig
from granular.evaluation.failure import FailureReport
from granular.evaluation.metric import (
    InferredDepEdge,
    InferredGraph,
    KAMetricResult,
    MetricResult,
)
from granular.evaluation.report import ReportBuilder
from granular.evaluation.reproduction import ReproductionReport
from granular.evaluation.runner import EvalRunner
from granular.inference.config import PipelineMode


def make_graph() -> InferredGraph:
    return InferredGraph(
        concept_to_course={"c1": "CS-25100", "c2": "CS-18000"},
        concept_to_area={"c1": "AL", "c2": "SDF"},
        edges=[InferredDepEdge("c1", "c2", 0.8)],
    )


class TestAblationRunner:
    def test_three_conditions(self):
        graph = make_graph()
        declared = {("CS-25100", "CS-18000")}
        held_out = [("CS-25100", "CS-18000")]

        def infer_fn(mode: PipelineMode) -> InferredGraph:
            # full pipeline recovers; degraded modes return empty graph
            if mode == PipelineMode.FULL_PIPELINE:
                return graph
            return InferredGraph(graph.concept_to_course, graph.concept_to_area, [])

        runner = AblationRunner(EvalConfig(), infer_fn)
        report = runner.run_all(held_out, declared)
        assert report.full_pipeline.recall == 1.0
        assert report.retrieval_only.recall == 0.0


class TestReportBuilder:
    def _report(self):
        cfg = EvalConfig()
        headline = {
            "all": MetricResult(0.8, 0.7, 0.75, 7, 2, 3, None),
            "high": MetricResult(0.9, 0.6, 0.72, 6, 1, 4, "high"),
            "medium": MetricResult(0.5, 0.4, 0.44, 2, 2, 3, "medium"),
            "low": MetricResult(0.2, 0.1, 0.13, 1, 4, 9, "low"),
        }
        from granular.evaluation.ablation import AblationReport
        ablation = AblationReport(
            retrieval_only=MetricResult(0.3, 0.2, 0.24, 2, 5, 8, None),
            retrieval_rerank=MetricResult(0.6, 0.5, 0.55, 5, 3, 5, None),
            full_pipeline=headline["all"],
        )
        by_area = [
            KAMetricResult("AL", "Algorithms", 0.8, 0.7, 0.75, 5, False),
            KAMetricResult("OS", "Operating Systems", 0.2, 0.2, 0.2, 3, True),
        ]
        repro = ReproductionReport(reproduces_declared_count=4, novel_count=6)
        failures = FailureReport(
            not_machine_checkable_rules=7,
            model_outputs_rejected=15,
            edges_removed_cycle_prevention=3,
            edges_rejected_ordering=2,
            poor_coverage_areas=["Operating Systems"],
        )
        return ReportBuilder().build(headline, by_area, ablation, repro, failures, cfg)

    def test_scope_statement_generated(self):
        report = self._report()
        assert "Purdue University" in report.scope_statement
        assert "Computer Science" in report.scope_statement
        assert "Modern Campus" in report.scope_statement

    def test_markdown_has_all_sections(self):
        report = self._report()
        md = ReportBuilder().to_markdown(report)
        assert "## Scope" in md
        assert "## Headline Metric" in md
        assert "## Knowledge-Area Breakdown" in md
        assert "## Ablation" in md
        assert "## Reproduction vs. Contribution" in md
        assert "## Failure Report" in md

    def test_failure_section_present_when_zero(self):
        cfg = EvalConfig()
        headline = {"all": MetricResult(0, 0, 0, 0, 0, 0, None)}
        from granular.evaluation.ablation import AblationReport
        ablation = AblationReport(
            MetricResult(0, 0, 0, 0, 0, 0, None),
            MetricResult(0, 0, 0, 0, 0, 0, None),
            MetricResult(0, 0, 0, 0, 0, 0, None),
        )
        failures = FailureReport()  # all zero
        report = ReportBuilder().build(headline, [], ablation, ReproductionReport(), failures, cfg)
        md = ReportBuilder().to_markdown(report)
        assert "## Failure Report" in md
        assert "none" in md  # poor-coverage areas: none

    def test_ablation_table_three_rows(self):
        report = self._report()
        md = ReportBuilder().to_markdown(report)
        assert "retrieval_only" in md
        assert "retrieval_rerank" in md
        assert "full_pipeline" in md


class TestEvalRunner:
    def test_full_run_produces_report(self, tmp_path):
        graph = make_graph()
        declared = {("CS-25100", "CS-18000")}

        def loader():
            return graph, declared

        cfg = EvalConfig(artefact_dir=tmp_path)
        runner = EvalRunner(cfg, loader)
        result = runner.run(run_id="run-test")

        assert "scope_statement" in result
        assert "headline" in result
        # Manifest and report artefacts should exist
        run_dir = tmp_path / "run-test"
        assert (run_dir / "run-test_report.json").exists()
        assert (run_dir / "run-test_report_md.md").exists()
        assert (run_dir / "run-test_manifest.json").exists()
