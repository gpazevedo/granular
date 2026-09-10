"""Tests for the alignment-precision eval."""

from __future__ import annotations

from granular.evaluation.alignment_eval import (
    AlignedConcept,
    evaluate_alignment_precision,
    sample_aligned_concepts,
)


def _concept(cid: str, area: str, label: str = "x", ku: str = "KU") -> AlignedConcept:
    return AlignedConcept(
        concept_id=cid,
        concept_label=label,
        course_id="CS-1",
        ku_id=ku,
        ku_label=ku,
        knowledge_area=area,
        confidence=0.6,
    )


class KeywordJudge:
    """Deterministic fake judge: belongs iff concept label == ku label."""

    def judge(self, concept_label: str, ku_label: str) -> bool:
        return concept_label == ku_label


class TestSampling:
    def test_stratified_covers_all_areas(self):
        concepts = (
            [_concept(f"a{i}", "AL") for i in range(10)]
            + [_concept(f"d{i}", "DS") for i in range(10)]
            + [_concept(f"o{i}", "OS") for i in range(10)]
        )
        sample = sample_aligned_concepts(concepts, sample_size=9, seed=42)
        areas = {c.knowledge_area for c in sample}
        assert areas == {"AL", "DS", "OS"}

    def test_deterministic_with_seed(self):
        concepts = [_concept(f"a{i}", "AL") for i in range(20)]
        s1 = [c.concept_id for c in sample_aligned_concepts(concepts, 5, seed=7)]
        s2 = [c.concept_id for c in sample_aligned_concepts(concepts, 5, seed=7)]
        assert s1 == s2

    def test_empty(self):
        assert sample_aligned_concepts([], 10, seed=1) == []


class TestPrecision:
    def test_precision_and_per_area(self):
        # AL: 2 correct (label==ku) + 1 wrong; DS: 1 wrong
        concepts = [
            _concept("1", "AL", label="KU", ku="KU"),
            _concept("2", "AL", label="KU", ku="KU"),
            _concept("3", "AL", label="other", ku="KU"),
            _concept("4", "DS", label="nope", ku="KU"),
        ]
        report = evaluate_alignment_precision(
            concepts, KeywordJudge(), sample_size=100, seed=42
        )
        assert report.judged == 4
        assert report.correct == 2
        assert report.precision == 0.5
        by_area = {a.knowledge_area: a for a in report.by_area}
        assert by_area["AL"].correct == 2 and by_area["AL"].judged == 3
        assert by_area["DS"].correct == 0 and by_area["DS"].judged == 1

    def test_report_to_dict(self):
        report = evaluate_alignment_precision(
            [_concept("1", "AL", label="KU", ku="KU")], KeywordJudge(), sample_size=10, seed=1
        )
        d = report.to_dict()
        assert d["precision"] == 1.0
        assert d["by_area"][0]["knowledge_area"] == "AL"
