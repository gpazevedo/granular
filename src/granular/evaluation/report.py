"""ReportBuilder — assembles JSON + Markdown evaluation reports. (Task 10)"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

from granular.evaluation.ablation import AblationReport
from granular.evaluation.config import EvalConfig
from granular.evaluation.failure import FailureReport
from granular.evaluation.judge import JudgementReport
from granular.evaluation.metric import KAMetricResult, MetricResult
from granular.evaluation.reproduction import ReproductionReport

SCOPE_TEMPLATE = (
    "This evaluation covers {institution} ({discipline}) courses from the "
    "{catalogue_year} catalogue (ingestion run {ingestion_run_id}). "
    "The genericity claim covers adapter genericity across the Modern Campus "
    "Acalog platform. Extraction genericity across disciplines has not been tested."
)


@dataclass
class EvalReport:
    scope_statement: str
    headline: dict[str, MetricResult]      # band -> result
    by_knowledge_area: list[KAMetricResult]
    ablation: AblationReport
    reproduction: ReproductionReport
    failures: FailureReport


class ReportBuilder:
    """Builds the final evaluation report in JSON and Markdown."""

    def build(
        self,
        headline: dict[str, MetricResult],
        by_area: list[KAMetricResult],
        ablation: AblationReport,
        reproduction: ReproductionReport,
        failures: FailureReport,
        config: EvalConfig,
    ) -> EvalReport:
        scope = SCOPE_TEMPLATE.format(
            institution=config.institution,
            discipline=config.discipline,
            catalogue_year=config.catalogue_year,
            ingestion_run_id=config.ingestion_run_id,
        )
        return EvalReport(
            scope_statement=scope,
            headline=headline,
            by_knowledge_area=by_area,
            ablation=ablation,
            reproduction=reproduction,
            failures=failures,
        )

    def to_json(self, report: EvalReport) -> dict:
        return {
            "scope_statement": report.scope_statement,
            "headline": {k: asdict(v) for k, v in report.headline.items()},
            "by_knowledge_area": [asdict(r) for r in report.by_knowledge_area],
            "ablation": {
                "retrieval_only": asdict(report.ablation.retrieval_only),
                "retrieval_rerank": asdict(report.ablation.retrieval_rerank),
                "full_pipeline": asdict(report.ablation.full_pipeline),
            },
            "reproduction": asdict(report.reproduction),
            "failures": asdict(report.failures),
        }

    def to_markdown(
        self,
        report: EvalReport,
        judgement_report: Optional[JudgementReport] = None,
    ) -> str:
        lines: list[str] = []
        lines.append("# Evaluation Report\n")

        # Section 1: Scope statement
        lines.append("## Scope\n")
        lines.append(report.scope_statement + "\n")

        # Section 2: Headline metric
        lines.append("## Headline Metric — Prerequisite Recovery (course-pair F1)\n")
        lines.append("| Confidence band | Precision | Recall | F1 | TP | FP | FN |")
        lines.append("|---|---|---|---|---|---|---|")
        for band in ("all", "high", "medium", "low"):
            m = report.headline.get(band)
            if m:
                lines.append(
                    f"| {band} | {m.precision:.3f} | {m.recall:.3f} | {m.f1:.3f} "
                    f"| {m.tp} | {m.fp} | {m.fn} |"
                )
        lines.append("")

        # Section 3: Knowledge-area breakdown
        lines.append("## Knowledge-Area Breakdown\n")
        lines.append("| Area | F1 | Precision | Recall | Sample | |")
        lines.append("|---|---|---|---|---|---|")
        for r in report.by_knowledge_area:
            flag = " ⚠" if r.poor_coverage else ""
            lines.append(
                f"| {r.knowledge_area_label} | {r.f1:.3f} | {r.precision:.3f} "
                f"| {r.recall:.3f} | {r.sample_size} |{flag} |"
            )
        lines.append("")

        # Section 4: Ablation
        lines.append("## Ablation\n")
        lines.append("| Condition | Precision | Recall | F1 |")
        lines.append("|---|---|---|---|")
        for name, m in [
            ("retrieval_only", report.ablation.retrieval_only),
            ("retrieval_rerank", report.ablation.retrieval_rerank),
            ("full_pipeline", report.ablation.full_pipeline),
        ]:
            lines.append(f"| {name} | {m.precision:.3f} | {m.recall:.3f} | {m.f1:.3f} |")
        lines.append("")

        # Section 5: Reproduction vs. contribution
        lines.append("## Reproduction vs. Contribution\n")
        rep = report.reproduction
        lines.append(f"- Reproduces declared: {rep.reproduces_declared_count}")
        lines.append(f"- Novel (contribution): {rep.novel_count}")
        lines.append("")

        # Section 6: Failure report (always present, even if zero)
        lines.append("## Failure Report\n")
        f = report.failures
        lines.append(f"- Requirement rules not machine-checkable: {f.not_machine_checkable_rules}")
        lines.append(f"- Model outputs rejected: {f.model_outputs_rejected}")
        lines.append(f"- Edges removed for cycle prevention: {f.edges_removed_cycle_prevention}")
        lines.append(f"- Edges rejected for ordering contradiction: {f.edges_rejected_ordering}")
        if f.poor_coverage_areas:
            lines.append(f"- Poor-coverage areas: {', '.join(f.poor_coverage_areas)}")
        else:
            lines.append("- Poor-coverage areas: none")
        lines.append("")

        # Section 7: Expert judgement (only if present)
        if judgement_report is not None:
            lines.append("## Expert Judgement (blinded)\n")
            jr = judgement_report
            lines.append(f"- Correct: {jr.correct_count}")
            lines.append(f"- Plausible but wrong: {jr.plausible_but_wrong_count}")
            lines.append(f"- Incorrect: {jr.incorrect_count}")
            lines.append("- Approval rate by confidence band:")
            for band, rate in jr.approval_by_confidence_band.items():
                lines.append(f"  - {band}: {rate:.2%}")
            lines.append("")

        return "\n".join(lines)
