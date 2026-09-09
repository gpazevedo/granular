"""CourseLevelSignal — dependency signal from relative course levels.

A concept in a higher-level course is more likely to depend on a concept in a
lower-level course. Reversed or same-level pairs score 0.
"""

from __future__ import annotations


def _normalise_level(course_number: str) -> float:
    try:
        first = int(course_number[:1])
    except (ValueError, IndexError):
        return 0.5
    return max(0.0, min(1.0, (first - 1) / 5.0))


def course_level_score(
    dependent_course_number: str,
    dependency_course_number: str,
) -> float:
    """Score how strongly the level difference supports A depends on B.

    dependent = A (higher expected), dependency = B (lower expected).
    Returns 0 if B is not lower than A.
    """
    level_a = _normalise_level(dependent_course_number)
    level_b = _normalise_level(dependency_course_number)
    diff = level_a - level_b
    if diff <= 0:
        return 0.0
    return min(1.0, diff)
