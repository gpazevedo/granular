"""Tests for CombinationBuilder (REQ-AQ-14)."""

from __future__ import annotations

from granular.api.services.combinator import build_combinations
from granular.api.services.matcher import CourseMatch


def course(cid, number, kus, relevance=0.8) -> CourseMatch:
    return CourseMatch(
        course_id=cid,
        course_number=number,
        subject_code="CS",
        title=f"Course {number}",
        level="undergraduate",
        credits="3",
        description_excerpt="",
        covered_ku_ids=list(kus),
        relevance_score=relevance,
    )


class TestBuildCombinations:
    def test_empty_input(self):
        assert build_combinations([], 5, set()) == []

    def test_combination_improves_coverage(self):
        # Each course covers 2 of 4 KUs; together they cover all 4.
        c1 = course("CS-1", "10000", ["k1", "k2"])
        c2 = course("CS-2", "20000", ["k3", "k4"])
        combos = build_combinations([c1, c2], total_resolved_kus=4, declared_prereqs=set())
        assert len(combos) == 1
        assert set(combos[0].combined_ku_ids) == {"k1", "k2", "k3", "k4"}
        assert combos[0].combined_coverage_breadth == "4 of 4 concepts"

    def test_no_improvement_excluded(self):
        # c2 is a subset of c1 → no combination improves on c1 alone
        c1 = course("CS-1", "10000", ["k1", "k2", "k3"])
        c2 = course("CS-2", "20000", ["k1"])
        combos = build_combinations([c1, c2], total_resolved_kus=3, declared_prereqs=set())
        assert combos == []

    def test_redundancy_flagged(self):
        c1 = course("CS-1", "10000", ["k1", "k2"])
        c2 = course("CS-2", "20000", ["k2", "k3"])   # k2 overlaps
        combos = build_combinations([c1, c2], total_resolved_kus=3, declared_prereqs=set())
        assert len(combos) == 1
        assert len(combos[0].redundancies) == 1
        assert combos[0].redundancies[0].overlapping_ku_ids == ["k2"]

    def test_prerequisite_order_declared(self):
        c1 = course("CS-25100", "25100", ["k1"])
        c2 = course("CS-18000", "18000", ["k2"])
        # 25100 requires 18000
        declared = {("CS-25100", "CS-18000")}
        combos = build_combinations([c1, c2], total_resolved_kus=2, declared_prereqs=declared)
        assert len(combos) == 1
        order = combos[0].prerequisite_order[0]
        assert order.declared is True
        assert order.take_first == "18000"
        assert order.then == "25100"

    def test_no_declared_ordering_noted(self):
        c1 = course("CS-1", "10000", ["k1"])
        c2 = course("CS-2", "20000", ["k2"])
        combos = build_combinations([c1, c2], total_resolved_kus=2, declared_prereqs=set())
        order = combos[0].prerequisite_order[0]
        assert order.declared is False
        assert "No ordering constraint is published" in order.message

    def test_max_size_capped_at_3(self):
        courses = [course(f"CS-{i}", f"{i}0000", [f"k{i}"]) for i in range(5)]
        combos = build_combinations(
            courses, total_resolved_kus=5, declared_prereqs=set(), max_size=3
        )
        # No combination should have more than 3 courses
        assert all(len(c.courses) <= 3 for c in combos)

    def test_max_results_capped(self):
        courses = [course(f"CS-{i}", f"{i}0000", [f"k{i}", f"k{i+10}"]) for i in range(6)]
        combos = build_combinations(
            courses, total_resolved_kus=20, declared_prereqs=set(), max_results=5
        )
        assert len(combos) <= 5
