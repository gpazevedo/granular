"""AdvisoryService — declared-layer advisory queries (readiness, unlock).

These queries traverse only the declared PREREQUISITE edges; they never touch
inferred concept edges. Every answer is labelled evidence_basis="declared".

Kept separate from FastAPI routing and DI so it is testable with a fake graph.
"""

from __future__ import annotations

from typing import Protocol

from granular.api.models.responses import (
    ReadinessResponse,
    UnlockedCourse,
    UnlockResponse,
    UnmetPrerequisite,
)


class AdvisoryGraphProtocol(Protocol):
    def course_exists(self, course_id: str) -> bool: ...
    def get_prerequisites(self, course_id: str) -> list[dict]: ...
    def get_unlocks(self, course_id: str) -> list[dict]: ...


class AdvisoryService:
    def __init__(self, graph: AdvisoryGraphProtocol) -> None:
        self._graph = graph

    def readiness(self, course_id: str, completed_courses: list[str]) -> ReadinessResponse:
        """Return declared prerequisites not satisfied by the completed list.

        The completed-course list is session-scoped input and is never persisted.
        """
        if not self._graph.course_exists(course_id):
            return ReadinessResponse(
                course_id=course_id,
                ready=False,
                unmet_prerequisites=[],
                status="course_not_found",
                status_message=f"No course '{course_id}' is present in the catalogue graph.",
            )

        completed = set(completed_courses)
        prereqs = self._graph.get_prerequisites(course_id)
        unmet = [
            UnmetPrerequisite(
                course_id=p["course_id"],
                title=p.get("title", ""),
                verbatim=p.get("verbatim", ""),
            )
            for p in prereqs
            if p["course_id"] not in completed
        ]
        return ReadinessResponse(
            course_id=course_id,
            ready=len(unmet) == 0,
            unmet_prerequisites=unmet,
        )

    def unlock(self, course_id: str) -> UnlockResponse:
        """Forward prerequisite traversal: courses this one helps open up."""
        if not self._graph.course_exists(course_id):
            return UnlockResponse(
                course_id=course_id,
                unlocks=[],
                status="course_not_found",
                status_message=f"No course '{course_id}' is present in the catalogue graph.",
            )

        unlocked = [
            UnlockedCourse(course_id=u["course_id"], title=u.get("title", ""))
            for u in self._graph.get_unlocks(course_id)
        ]
        return UnlockResponse(course_id=course_id, unlocks=unlocked)
