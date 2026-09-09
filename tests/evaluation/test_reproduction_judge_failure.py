"""Tests for ReproductionClassifier, JudgementSetBuilder, FailureReporter (Tasks 5, 6, 7)."""

from __future__ import annotations

import json

from granular.evaluation.config import EvalConfig
from granular.evaluation.failure import FailureReporter
from granular.evaluation.judge import (
    CandidateEdge,
    JudgementAnalyser,
    JudgementSetBuilder,
)
from granular.evaluation.metric import InferredDepEdge, InferredGraph, KAMetricResult
from granular.evaluation.reproduction import EdgeClass, ReproductionClassifier
from granular.evaluation.artefacts import ArtefactStore


def make_graph() -> InferredGraph:
    return InferredGraph(
        concept_to_course={"c1": "CS-25100", "c2": "CS-18000", "c3": "CS-30000"},
        concept_to_area={"c1": "AL", "c2": "SDF", "c3": "AL"},
        edges=[
            InferredDepEdge("c1", "c2", 0.8),   # reproduces declared 25100->18000
            InferredDepEdge("c3", "c1", 0.6),   # novel 30000->25100
        ],
    )


class TestReproductionClassifier:
    def test_classifies_reproduced_and_novel(self):
        graph = make_graph()
        declared = {("CS-25100", "CS-18000")}
        clf = ReproductionClassifier(graph, declared)
        assert clf.classify("c1", "c2") == EdgeClass.REPRODUCES_DECLARED
        assert clf.classify("c3", "c1") == EdgeClass.NOVEL

    def test_classify_all_counts(self):
        graph = make_graph()
        declared = {("CS-25100", "CS-18000")}
        report = ReproductionClassifier(graph, declared).classify_all()
        assert report.reproduces_declared_count == 1
        assert report.novel_count == 1


class TestJudgementSetBuilder:
    def _candidates(self, is_inferred: bool, n: int, area: str = "AL") -> list[CandidateEdge]:
        return [
            CandidateEdge(
                item_id=f"{'inf' if is_inferred else 'dist'}-{i}",
                concept_a_label=f"A{i}",
                concept_a_course="CS-30000",
                concept_b_label=f"B{i}",
                concept_b_course="CS-25100",
                knowledge_area=area,
                is_inferred=is_inferred,
                confidence=0.8 if is_inferred else 0.0,
            )
            for i in range(n)
        ]

    def test_blind_set_has_no_labels(self, tmp_path):
        novel = self._candidates(True, 4, "AL") + self._candidates(True, 4, "IS")
        distractors = self._candidates(False, 8)
        cfg = EvalConfig()
        builder = JudgementSetBuilder()
        jset = builder.build(novel, distractors, sample_size=4, distractor_ratio=1.0, config=cfg)

        store = ArtefactStore(tmp_path)
        store.init_run("run-1")
        builder.write_rubric(store)
        builder.write_blind(jset, store)

        blind_file = store.run_dir / "run-1_judgement_set_blind.json"
        data = json.loads(blind_file.read_text())
        for item in data["items"]:
            assert "is_inferred" not in item
            assert "confidence" not in item

    def test_rubric_written(self, tmp_path):
        store = ArtefactStore(tmp_path)
        store.init_run("run-1")
        JudgementSetBuilder().write_rubric(store)
        rubric = store.run_dir / "run-1_rubric.md"
        assert rubric.exists()
        assert "correct" in rubric.read_text()

    def test_stratified_across_areas(self):
        novel = self._candidates(True, 5, "AL") + self._candidates(True, 5, "IS") + self._candidates(True, 5, "OS")
        cfg = EvalConfig()
        jset = JudgementSetBuilder().build(novel, [], sample_size=6, distractor_ratio=0.0, config=cfg)
        areas = {i.knowledge_area for i in jset.items}
        assert len(areas) >= 2


class TestJudgementAnalyser:
    def test_analyse_by_confidence_band(self):
        candidates = [
            CandidateEdge("i1", "A", "C1", "B", "C2", "AL", True, 0.9),   # high
            CandidateEdge("i2", "A", "C1", "B", "C2", "AL", True, 0.5),   # medium
        ]
        labels = {"i1": "correct", "i2": "incorrect"}
        cfg = EvalConfig()
        report = JudgementAnalyser().analyse(labels, candidates, cfg)
        assert report.correct_count == 1
        assert report.incorrect_count == 1
        assert report.approval_by_confidence_band["high"] == 1.0
        assert report.approval_by_confidence_band["medium"] == 0.0

    def test_load_labels_validates(self, tmp_path):
        p = tmp_path / "labelled.json"
        p.write_text(json.dumps({"items": [{"item_id": "i1", "label": "correct"}]}))
        labels = JudgementAnalyser().load_labels(p)
        assert labels["i1"] == "correct"

    def test_load_labels_rejects_invalid(self, tmp_path):
        p = tmp_path / "labelled.json"
        p.write_text(json.dumps({"items": [{"item_id": "i1", "label": "maybe"}]}))
        import pytest
        with pytest.raises(ValueError):
            JudgementAnalyser().load_labels(p)


class TestFailureReporter:
    def test_all_fields_present_when_empty(self):
        report = FailureReporter().collect(None, None, None, [])
        assert report.not_machine_checkable_rules == 0
        assert report.model_outputs_rejected == 0
        assert report.edges_removed_cycle_prevention == 0
        assert report.edges_rejected_ordering == 0
        assert report.poor_coverage_areas == []

    def test_collects_from_summaries(self):
        report = FailureReporter().collect(
            inference_summary={"edges_rejected_cycle": 3, "edges_rejected_ordering": 2},
            extraction_summary={"concepts_unaligned": 10, "concepts_low_confidence": 5},
            ingestion_summary={"prereqs_unstructured": 7},
            ka_results=[
                KAMetricResult("AL", "Algorithms", 0.2, 0.2, 0.2, 5, poor_coverage=True),
            ],
        )
        assert report.not_machine_checkable_rules == 7
        assert report.model_outputs_rejected == 15
        assert report.edges_removed_cycle_prevention == 3
        assert report.edges_rejected_ordering == 2
        assert "Algorithms" in report.poor_coverage_areas
