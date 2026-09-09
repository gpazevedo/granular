"""CourseMatcher data structures and ranking (pure, testable)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CourseMatch:
    course_id: str
    course_number: str
    subject_code: str
    title: str
    level: str
    credits: str
    description_excerpt: str
    covered_ku_ids: list[str]
    relevance_score: float   # mean alignment confidence of matched concepts


def coverage_breadth(covered: int, total: int) -> str:
    return f"{covered} of {total} concepts"


def rank_courses(
    matches: list[CourseMatch],
    total_resolved_kus: int,
) -> list[CourseMatch]:
    """Sort matches by relevance descending, coverage breadth as tiebreaker."""
    return sorted(
        matches,
        key=lambda m: (m.relevance_score, len(m.covered_ku_ids)),
        reverse=True,
    )
