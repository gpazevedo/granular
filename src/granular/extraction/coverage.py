"""CoverageIndex — maps knowledge units to the courses that cover them.

Used by the advisory query layer to detect thin coverage.
"""

from __future__ import annotations

from collections import defaultdict

from granular.schema import AlignmentStatus, Concept


class CoverageIndex:
    """Index of knowledge_unit_id -> set of course_ids that cover it."""

    def __init__(self) -> None:
        self._ku_to_courses: dict[str, set[str]] = defaultdict(set)

    def build(self, concepts: list[Concept]) -> None:
        """Build the index from aligned concepts."""
        for concept in concepts:
            if (
                concept.alignment_status == AlignmentStatus.ALIGNED
                and concept.knowledge_unit_id
            ):
                self._ku_to_courses[concept.knowledge_unit_id].add(
                    concept.source_course_id
                )

    def courses_for_ku(self, ku_id: str) -> list[str]:
        return sorted(self._ku_to_courses.get(ku_id, set()))

    def thin_coverage_units(self, min_courses: int = 1) -> list[str]:
        """Return knowledge units covered by fewer than min_courses courses."""
        return [
            ku_id
            for ku_id, courses in self._ku_to_courses.items()
            if len(courses) < min_courses
        ]

    def coverage_count(self, ku_id: str) -> int:
        return len(self._ku_to_courses.get(ku_id, set()))
