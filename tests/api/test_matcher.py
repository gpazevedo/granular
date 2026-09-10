"""Tests for course ranking (composite coverage-weighted relevance)."""

from __future__ import annotations

from granular.api.services.matcher import (
    CourseMatch,
    composite_score,
    coverage_breadth,
    rank_courses,
)


def _match(course_id: str, covered: list[str], relevance: float) -> CourseMatch:
    return CourseMatch(
        course_id=course_id,
        course_number=course_id.split("-")[-1],
        subject_code="CS",
        title=course_id,
        level="undergraduate",
        credits="",
        description_excerpt="",
        covered_ku_ids=covered,
        relevance_score=relevance,
    )


class TestCompositeScore:
    def test_coverage_fraction_times_confidence(self):
        # 5 of 10 KUs at 0.6 -> 0.30
        assert composite_score(5, 10, 0.6) == 0.30

    def test_zero_total_is_safe(self):
        assert composite_score(3, 0, 0.9) == 0.0


class TestRanking:
    def test_broad_coverage_beats_narrow_high_confidence(self):
        # Regression: a single high-confidence match must NOT outrank a course
        # that covers many resolved KUs at moderate confidence.
        narrow = _match("CS-999", covered=["KU-1"], relevance=0.97)          # 1/14 * 0.97 = 0.069
        broad = _match("CS-440", covered=["KU-1", "KU-2", "KU-3", "KU-4", "KU-5"], relevance=0.60)  # 5/14 * 0.6 = 0.214
        ranked = rank_courses([narrow, broad], total_resolved_kus=14)
        assert ranked[0].course_id == "CS-440"
        assert ranked[1].course_id == "CS-999"

    def test_tiebreak_by_coverage_then_confidence(self):
        # Equal composite is unlikely, but coverage count breaks ties before confidence.
        a = _match("CS-1", covered=["KU-1", "KU-2"], relevance=0.5)   # 2/10 * 0.5 = 0.10
        b = _match("CS-2", covered=["KU-1"], relevance=1.0)           # 1/10 * 1.0 = 0.10
        ranked = rank_courses([a, b], total_resolved_kus=10)
        assert ranked[0].course_id == "CS-1"  # more coverage wins the tie

    def test_coverage_breadth_string(self):
        assert coverage_breadth(3, 14) == "3 of 14 concepts"
