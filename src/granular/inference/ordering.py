"""OrderingValidator — rejects inferred edges that contradict declared prerequisites."""

from __future__ import annotations

from enum import Enum

from granular.inference.scorer import ConceptNode
from granular.inference.signals.prerequisite_prior import PrerequisitePrior


class ValidationResult(str, Enum):
    OK = "ok"
    CONTRADICTION = "contradiction"


class OrderingValidator:
    """Checks that an inferred concept dependency does not contradict a
    declared course-level prerequisite in the opposite direction.
    """

    def __init__(self, prereq_prior: PrerequisitePrior) -> None:
        self._prereq = prereq_prior

    def check(self, dependent: ConceptNode, dependency: ConceptNode) -> ValidationResult:
        """Inferred: dependent depends on dependency (A → B).

        Contradiction if the declared prerequisites say course_B requires
        course_A (i.e. the declared direction is the opposite of the inferred).
        """
        # If B's course declares A's course as a prerequisite, then B comes
        # after A at the course level — contradicting "A depends on B".
        reverse_score = self._prereq.score(
            dependency.source_course_id, dependent.source_course_id
        )
        if reverse_score >= 1.0:
            return ValidationResult.CONTRADICTION
        return ValidationResult.OK
