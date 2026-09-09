"""MetricCalculator — precision, recall, F1 at course-pair level. (Task 4)"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Optional


@dataclass
class InferredDepEdge:
    from_concept: str
    to_concept: str
    confidence: float


@dataclass
class InferredGraph:
    """Lightweight view of the inferred concept dependency graph for metrics.

    - concept_to_course: concept_id -> course_id
    - concept_to_area: concept_id -> knowledge_area
    - edges: directed DEPENDS_ON edges with confidence
    """

    concept_to_course: dict[str, str]
    concept_to_area: dict[str, str]
    edges: list[InferredDepEdge]

    def adjacency(self, confidence_filter: Optional[tuple[float, float]] = None) -> dict[str, set[str]]:
        adj: dict[str, set[str]] = defaultdict(set)
        for e in self.edges:
            if confidence_filter is not None:
                lo, hi = confidence_filter
                if not (lo <= e.confidence < hi):
                    continue
            adj[e.from_concept].add(e.to_concept)
        return adj

    def concepts_in_course(self, course_id: str) -> set[str]:
        return {c for c, crs in self.concept_to_course.items() if crs == course_id}


@dataclass
class MetricResult:
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    confidence_filter: Optional[str] = None


@dataclass
class KAMetricResult:
    knowledge_area: str
    knowledge_area_label: str
    precision: float
    recall: float
    f1: float
    sample_size: int
    poor_coverage: bool


_BAND_RANGES = {
    "high": (0.70, 1.01),
    "medium": (0.40, 0.70),
    "low": (0.0, 0.40),
}


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


class MetricCalculator:
    """Computes prerequisite-recovery metrics over the inferred concept graph."""

    def __init__(self, max_depth: int = 5) -> None:
        self._max_depth = max_depth

    def _has_path_between_courses(
        self,
        adj: dict[str, set[str]],
        graph: InferredGraph,
        course_from: str,
        course_to: str,
    ) -> bool:
        """True if any concept in course_from reaches any concept in course_to
        via DEPENDS_ON edges within max_depth hops.
        """
        start_concepts = graph.concepts_in_course(course_from)
        target_concepts = graph.concepts_in_course(course_to)
        if not start_concepts or not target_concepts:
            return False

        visited: set[str] = set(start_concepts)
        queue: deque[tuple[str, int]] = deque((c, 0) for c in start_concepts)
        while queue:
            node, depth = queue.popleft()
            if node in target_concepts and depth > 0:
                return True
            if depth >= self._max_depth:
                continue
            for neighbour in adj.get(node, set()):
                if neighbour in target_concepts:
                    return True
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append((neighbour, depth + 1))
        return False

    def compute(
        self,
        held_out: list[tuple[str, str]],   # (course_X, course_Y): X requires Y
        graph: InferredGraph,
        all_declared: set[tuple[str, str]],
        confidence_filter: Optional[str] = None,
    ) -> MetricResult:
        """Compute precision/recall/F1 at course-pair level.

        A withheld (X, Y) is TP if a concept path Y->X exists in the inferred graph.
        FP: an inferred course-pair path not in any declared prerequisite.
        """
        band_range = _BAND_RANGES.get(confidence_filter) if confidence_filter else None
        adj = graph.adjacency(band_range)

        tp = 0
        fn = 0
        # For each withheld prereq (X requires Y), X is the dependent and Y the
        # prerequisite. Inferred DEPENDS_ON edges point dependent -> dependency,
        # so we expect a concept path from a concept in X to a concept in Y.
        for course_x, course_y in held_out:
            if self._has_path_between_courses(adj, graph, course_x, course_y):
                tp += 1
            else:
                fn += 1

        # False positives: inferred course-pair paths not backed by any declared prereq.
        courses = set(graph.concept_to_course.values())
        fp = 0
        declared_pairs = all_declared  # (course, prereq) == (dependent, dependency)
        for course_x in courses:
            for course_y in courses:
                if course_x == course_y:
                    continue
                # path from X to Y implies inferred "X requires Y"
                if self._has_path_between_courses(adj, graph, course_x, course_y):
                    if (course_x, course_y) not in declared_pairs:
                        fp += 1

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        return MetricResult(
            precision=precision,
            recall=recall,
            f1=_f1(precision, recall),
            tp=tp,
            fp=fp,
            fn=fn,
            confidence_filter=confidence_filter,
        )

    def compute_all_bands(
        self,
        held_out: list[tuple[str, str]],
        graph: InferredGraph,
        all_declared: set[tuple[str, str]],
    ) -> dict[str, MetricResult]:
        return {
            "all": self.compute(held_out, graph, all_declared, None),
            "high": self.compute(held_out, graph, all_declared, "high"),
            "medium": self.compute(held_out, graph, all_declared, "medium"),
            "low": self.compute(held_out, graph, all_declared, "low"),
        }

    def compute_by_knowledge_area(
        self,
        held_out: list[tuple[str, str]],
        graph: InferredGraph,
        all_declared: set[tuple[str, str]],
        ka_labels: dict[str, str],
        poor_threshold: float,
    ) -> list[KAMetricResult]:
        """Group held-out edges by the KA of the prerequisite course's concepts."""
        by_area: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for course_x, course_y in held_out:
            # Determine the KA from the prerequisite course's concepts
            areas = {
                graph.concept_to_area.get(c, "")
                for c in graph.concepts_in_course(course_y)
            }
            areas.discard("")
            area = next(iter(areas)) if areas else "UNKNOWN"
            by_area[area].append((course_x, course_y))

        results: list[KAMetricResult] = []
        for area, edges in sorted(by_area.items()):
            m = self.compute(edges, graph, all_declared, None)
            results.append(
                KAMetricResult(
                    knowledge_area=area,
                    knowledge_area_label=ka_labels.get(area, area),
                    precision=m.precision,
                    recall=m.recall,
                    f1=m.f1,
                    sample_size=len(edges),
                    poor_coverage=m.f1 < poor_threshold,
                )
            )
        return results
