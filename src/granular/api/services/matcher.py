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


def composite_score(
    covered_count: int,
    total_resolved_kus: int,
    mean_confidence: float,
) -> float:
    """Composite ranking score combining coverage breadth and relevance.

    Coverage breadth is the dominant signal: a course covering many of the
    resolved knowledge units is more relevant to the query than one covering a
    single unit at high per-concept confidence. Mean alignment confidence acts
    as a quality weight on top of coverage.

        score = coverage_fraction * mean_confidence

    This fixes ranking-by-mean-confidence, which surfaced narrow high-confidence
    matches (e.g. a single loosely-related concept) above broad-coverage courses.
    """
    if total_resolved_kus <= 0:
        return 0.0
    coverage_fraction = covered_count / total_resolved_kus
    return coverage_fraction * mean_confidence


def rank_courses(
    matches: list[CourseMatch],
    total_resolved_kus: int,
) -> list[CourseMatch]:
    """Sort matches by composite score (coverage-weighted relevance).

    Tiebreakers: raw coverage count, then mean confidence — both descending.
    """
    return sorted(
        matches,
        key=lambda m: (
            composite_score(len(m.covered_ku_ids), total_resolved_kus, m.relevance_score),
            len(m.covered_ku_ids),
            m.relevance_score,
        ),
        reverse=True,
    )
