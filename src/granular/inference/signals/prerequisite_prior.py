"""PrerequisitePriorSignal — dependency signal from declared course prerequisites.

The strongest signal when available: if the course containing A declares a
prerequisite on the course containing B (directly or transitively), that
supports the inferred concept dependency A depends on B.
"""

from __future__ import annotations


class PrerequisitePrior:
    """Precomputes transitive declared-prerequisite reachability."""

    def __init__(self, declared_prereqs: set[tuple[str, str]]) -> None:
        # declared_prereqs: set of (course_id, prereq_course_id)
        self._direct: dict[str, set[str]] = {}
        for course, prereq in declared_prereqs:
            self._direct.setdefault(course, set()).add(prereq)

    def score(
        self,
        dependent_course: str,
        dependency_course: str,
    ) -> float:
        """Return a score in [0, 1] for the declared-prerequisite support.

        1.0  — direct declared prerequisite
        0.5  — transitive at depth 1
        0.3  — transitive at depth 2–3
        0.0  — no declared prerequisite relationship
        """
        if dependent_course == dependency_course:
            return 0.0

        # Direct
        if dependency_course in self._direct.get(dependent_course, set()):
            return 1.0

        # BFS over transitive prerequisites.
        # "hops" counts edges from dependent_course to dependency_course.
        # Direct (1 hop) is handled above. 2 hops → 0.5, 3–4 hops → 0.3.
        visited = {dependent_course}
        frontier = list(self._direct.get(dependent_course, set()))
        hops = 1  # frontier currently holds nodes 1 hop away
        while frontier and hops <= 4:
            next_frontier: list[str] = []
            for node in frontier:
                if node in visited:
                    continue
                visited.add(node)
                next_frontier.extend(self._direct.get(node, set()))
            hops += 1
            if dependency_course in next_frontier:
                return 0.5 if hops == 2 else 0.3
            frontier = next_frontier

        return 0.0
