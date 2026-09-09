"""DependencyScorer — combines the three structural signals into a candidate score."""

from __future__ import annotations

from dataclasses import dataclass

from granular.inference.config import InferenceConfig
from granular.inference.signals.course_level import course_level_score
from granular.inference.signals.ku_cooccurrence import ku_cooccurrence_score
from granular.inference.signals.prerequisite_prior import PrerequisitePrior


@dataclass
class ConceptNode:
    concept_id: str
    label: str
    source_course_id: str
    course_number: str
    knowledge_area: str  # "" if unaligned


class DependencyScorer:
    """Combines course-level, prerequisite-prior, and KU-cooccurrence signals.

    No embedding similarity contributes to the edge decision — this is a
    purely structural score, as required by the design.
    """

    def __init__(self, config: InferenceConfig, prereq_prior: PrerequisitePrior) -> None:
        self._config = config
        self._weights = config.signal_weights
        self._prereq = prereq_prior

    def score(self, dependent: ConceptNode, dependency: ConceptNode) -> float:
        """Score the hypothesis that `dependent` depends on `dependency`."""
        level = course_level_score(dependent.course_number, dependency.course_number)
        prereq = self._prereq.score(
            dependent.source_course_id, dependency.source_course_id
        )
        cooccur = ku_cooccurrence_score(
            dependent.knowledge_area, dependency.knowledge_area
        )

        return (
            self._weights.course_level * level
            + self._weights.prerequisite_prior * prereq
            + self._weights.ku_cooccurrence * cooccur
        )
