"""ReproductionClassifier — separate reproduced vs. novel inferred edges. (Task 5)"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from granular.evaluation.metric import InferredGraph


class EdgeClass(str, Enum):
    REPRODUCES_DECLARED = "reproduces_declared"
    NOVEL = "novel"


@dataclass
class ReproductionReport:
    reproduces_declared_count: int = 0
    novel_count: int = 0
    reproduces_declared_confidences: list[float] = field(default_factory=list)
    novel_confidences: list[float] = field(default_factory=list)


class ReproductionClassifier:
    """Classifies inferred dependency edges as reproducing declared or novel."""

    def __init__(self, graph: InferredGraph, all_declared: set[tuple[str, str]]) -> None:
        self._graph = graph
        self._declared = all_declared

    def classify(self, from_concept: str, to_concept: str) -> EdgeClass:
        """An edge from A (course X) to B (course Y) reproduces a declared fact
        if (X, Y) is a declared prerequisite. Otherwise novel.
        """
        course_x = self._graph.concept_to_course.get(from_concept)
        course_y = self._graph.concept_to_course.get(to_concept)
        if course_x and course_y and (course_x, course_y) in self._declared:
            return EdgeClass.REPRODUCES_DECLARED
        return EdgeClass.NOVEL

    def classify_all(self) -> ReproductionReport:
        report = ReproductionReport()
        for edge in self._graph.edges:
            cls = self.classify(edge.from_concept, edge.to_concept)
            if cls == EdgeClass.REPRODUCES_DECLARED:
                report.reproduces_declared_count += 1
                report.reproduces_declared_confidences.append(edge.confidence)
            else:
                report.novel_count += 1
                report.novel_confidences.append(edge.confidence)
        return report
