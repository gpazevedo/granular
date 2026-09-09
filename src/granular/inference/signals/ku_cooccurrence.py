"""KUCooccurrenceSignal — dependency signal from knowledge-area co-occurrence."""

from __future__ import annotations


def ku_cooccurrence_score(
    dependent_ku_area: str,
    dependency_ku_area: str,
    same_area_bonus: float = 1.0,
    adjacent_area_bonus: float = 0.5,
) -> float:
    """Score based on knowledge-area relationship between the two concepts.

    Same knowledge area → strong signal (concepts likely build on each other).
    Different area → weaker signal.
    """
    if dependent_ku_area == dependency_ku_area:
        return same_area_bonus
    return adjacent_area_bonus
