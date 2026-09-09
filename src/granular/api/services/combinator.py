"""CombinationBuilder — course combinations that improve coverage (pure, testable).

Implements REQ-AQ-14: combinations of 2–3 courses that together cover more
resolved knowledge units than any single course. Reports redundancy per pair
and prerequisite ordering from declared edges.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from granular.api.services.matcher import CourseMatch, coverage_breadth


@dataclass
class RedundancyNote:
    course_a_number: str
    course_b_number: str
    overlapping_ku_ids: list[str]


@dataclass
class PrereqNote:
    take_first: str
    then: str
    declared: bool
    message: str = ""


@dataclass
class Combination:
    courses: list[CourseMatch]
    combined_ku_ids: list[str]
    combined_coverage_breadth: str
    redundancies: list[RedundancyNote]
    prerequisite_order: list[PrereqNote]
    combined_relevance: float


def build_combinations(
    courses: list[CourseMatch],
    total_resolved_kus: int,
    declared_prereqs: set[tuple[str, str]],   # (course_id, prereq_course_id)
    max_size: int = 3,
    max_results: int = 5,
    search_pool: int = 20,
) -> list[Combination]:
    """Build course combinations that improve on the best single-course coverage.

    Only combinations that add knowledge-unit coverage beyond the best single
    member are returned. Sizes 2..max_size are considered.
    """
    if not courses:
        return []

    pool = courses[: min(search_pool, len(courses))]
    best_single_coverage = max(len(c.covered_ku_ids) for c in pool)

    results: list[Combination] = []

    for size in range(2, max_size + 1):
        for combo in combinations(pool, size):
            union: set[str] = set()
            for c in combo:
                union.update(c.covered_ku_ids)

            # Must improve on the best single-course coverage
            if len(union) <= best_single_coverage:
                continue

            # Redundancy per pair
            redundancies: list[RedundancyNote] = []
            for a, b in combinations(combo, 2):
                overlap = sorted(set(a.covered_ku_ids) & set(b.covered_ku_ids))
                if overlap:
                    redundancies.append(
                        RedundancyNote(
                            course_a_number=a.course_number,
                            course_b_number=b.course_number,
                            overlapping_ku_ids=overlap,
                        )
                    )

            # Prerequisite ordering from declared edges
            prereq_order = _prereq_notes(combo, declared_prereqs)

            combined_relevance = sum(c.relevance_score for c in combo) / len(combo)

            results.append(
                Combination(
                    courses=list(combo),
                    combined_ku_ids=sorted(union),
                    combined_coverage_breadth=coverage_breadth(len(union), total_resolved_kus),
                    redundancies=redundancies,
                    prerequisite_order=prereq_order,
                    combined_relevance=combined_relevance,
                )
            )

    # Sort by union size desc, then combined relevance desc
    results.sort(key=lambda c: (len(c.combined_ku_ids), c.combined_relevance), reverse=True)
    return results[:max_results]


def _prereq_notes(
    combo: tuple[CourseMatch, ...],
    declared_prereqs: set[tuple[str, str]],
) -> list[PrereqNote]:
    notes: list[PrereqNote] = []
    found_any = False
    for a, b in combinations(combo, 2):
        # a requires b → take b first
        if (a.course_id, b.course_id) in declared_prereqs:
            notes.append(PrereqNote(take_first=b.course_number, then=a.course_number, declared=True))
            found_any = True
        elif (b.course_id, a.course_id) in declared_prereqs:
            notes.append(PrereqNote(take_first=a.course_number, then=b.course_number, declared=True))
            found_any = True

    if not found_any:
        notes.append(
            PrereqNote(
                take_first="",
                then="",
                declared=False,
                message="No ordering constraint is published between these courses.",
            )
        )
    return notes
