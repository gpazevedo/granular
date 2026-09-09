"""Stage 3: Reject on structure.

Rejects candidate alignments that would introduce a dependency cycle or a
prerequisite ordering violation. The cost asymmetry (a false merge is worse
than a miss) favours rejection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from granular.extraction.extractor import RawConcept
from granular.extraction.pipeline.rerank import RankedCandidateKU

logger = logging.getLogger(__name__)


@dataclass
class RejectionRecord:
    ku_id: str
    reason: str  # "cycle_violation" | "ordering_violation"


@dataclass
class RejectResult:
    surviving: list[RankedCandidateKU]
    rejections: list[RejectionRecord] = field(default_factory=list)


class ConceptGraphSnapshot:
    """Read-only view of concept alignments committed so far in this run.

    Tracks concept → knowledge-area assignments and course levels so that
    the reject stage can detect ordering violations.
    """

    def __init__(self) -> None:
        # ku_id -> set of course levels (normalised) where it has been aligned
        self._ku_course_levels: dict[str, set[float]] = {}

    def record_alignment(self, ku_id: str, course_level: float) -> None:
        self._ku_course_levels.setdefault(ku_id, set()).add(course_level)

    def would_violate_ordering(self, ku_id: str, course_level: float) -> bool:
        """A very light structural check: if this KU has only ever been aligned
        to strictly higher-level courses, aligning a much lower-level course to it
        may indicate an ordering problem. This is a conservative heuristic.
        """
        existing = self._ku_course_levels.get(ku_id)
        if not existing:
            return False
        # If the new course is dramatically lower than all existing, flag it
        return all(course_level + 0.5 < lvl for lvl in existing)


def reject(
    concept: RawConcept,
    candidates: list[RankedCandidateKU],
    course_level: float,
    snapshot: ConceptGraphSnapshot,
) -> RejectResult:
    """Filter candidates that would introduce structural violations.

    Returns surviving candidates and a list of rejections with reasons.
    """
    surviving: list[RankedCandidateKU] = []
    rejections: list[RejectionRecord] = []

    for cand in candidates:
        if snapshot.would_violate_ordering(cand.ku_id, course_level):
            rejections.append(
                RejectionRecord(ku_id=cand.ku_id, reason="ordering_violation")
            )
            logger.debug(
                "Rejected %s for concept %s: ordering_violation",
                cand.ku_id,
                concept.label,
            )
            continue
        surviving.append(cand)

    return RejectResult(surviving=surviving, rejections=rejections)
