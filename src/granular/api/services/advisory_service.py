"""AdvisoryService — declared-layer advisory queries (readiness, unlock).

These queries traverse only the declared PREREQUISITE edges; they never touch
inferred concept edges. Every answer is labelled evidence_basis="declared".

Kept separate from FastAPI routing and DI so it is testable with a fake graph.
"""

from __future__ import annotations

from typing import Protocol

from granular.api.models.responses import (
    OverlapConcept,
    OverlapResponse,
    ReadinessResponse,
    UnlockedCourse,
    UnlockResponse,
    UnmetPrerequisite,
)


class AdvisoryGraphProtocol(Protocol):
    def course_exists(self, course_id: str) -> bool: ...
    def get_prerequisites(self, course_id: str) -> list[dict]: ...
    def get_unlocks(self, course_id: str) -> list[dict]: ...
    def course_concepts(self, course_id: str) -> list[dict]: ...
    def covered_ku_ids(self, course_ids: list[str]) -> set[str]: ...


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

    def overlap(self, course_id: str, completed_courses: list[str]) -> OverlapResponse:
        """Which of the target course's concepts are already covered by the
        completed courses (matched) and which are not (gaps), at CS2023
        knowledge-unit grain. Evidence basis inferred; never implies exemption.

        The completed-course list is session-scoped input and is never persisted.
        """
        if not self._graph.course_exists(course_id):
            return OverlapResponse(
                course_id=course_id,
                matched_concepts=[],
                gap_concepts=[],
                confidence=0.0,
                status="course_not_found",
                status_message=f"No course '{course_id}' is present in the catalogue graph.",
            )

        # Target course concepts at KU grain; keep the max confidence per KU.
        target = self._graph.course_concepts(course_id)
        ku_info: dict[str, dict] = {}
        ku_conf: dict[str, float] = {}
        for row in target:
            ku_id = row["ku_id"]
            ku_info.setdefault(
                ku_id,
                {"label": row["ku_label"], "knowledge_area": row["knowledge_area"]},
            )
            ku_conf[ku_id] = max(ku_conf.get(ku_id, 0.0), row["confidence"])

        # KUs covered by the completed courses (exclude the target itself).
        completed = [c for c in completed_courses if c != course_id]
        covered = self._graph.covered_ku_ids(completed)

        matched_ids = [k for k in ku_info if k in covered]
        gap_ids = [k for k in ku_info if k not in covered]

        def to_concept(k: str) -> OverlapConcept:
            return OverlapConcept(
                ku_id=k,
                label=ku_info[k]["label"],
                knowledge_area=ku_info[k]["knowledge_area"],
            )

        # Confidence: mean alignment confidence over the matched KUs (0 if none).
        confidence = (
            sum(ku_conf[k] for k in matched_ids) / len(matched_ids)
            if matched_ids
            else 0.0
        )

        return OverlapResponse(
            course_id=course_id,
            matched_concepts=[to_concept(k) for k in matched_ids],
            gap_concepts=[to_concept(k) for k in gap_ids],
            confidence=round(confidence, 3),
        )
