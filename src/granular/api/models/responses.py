"""Pydantic request/response models for the advisory API."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Level = Literal["undergraduate", "graduate", "all"]

CAVEAT = (
    "Coverage is inferred from course descriptions and may not reflect "
    "actual course content."
)


class DiscoverRequest(BaseModel):
    query: str = Field(..., min_length=1)
    level: Level = "all"


class KULabel(BaseModel):
    ku_id: str
    label: str
    knowledge_area: str


class CourseResult(BaseModel):
    course_id: str
    course_number: str
    subject_code: str
    title: str
    level: str
    credits: str
    description_excerpt: str
    relevance_score: float
    coverage_breadth: str          # "N of M concepts"
    covered_ku_ids: list[str]
    evidence_basis: Literal["inferred"] = "inferred"
    confidence: float
    caveat: str = CAVEAT


class RedundancyNote(BaseModel):
    course_a_number: str
    course_b_number: str
    overlapping_ku_labels: list[str]


class PrereqNote(BaseModel):
    take_first: str
    then: str
    declared: bool
    message: Optional[str] = None


class CombinationResult(BaseModel):
    course_numbers: list[str]
    course_titles: list[str]
    combined_coverage_breadth: str
    combined_ku_ids: list[str]
    redundancies: list[RedundancyNote]
    prerequisite_order: list[PrereqNote]
    combined_relevance: float
    evidence_basis: Literal["inferred"] = "inferred"
    caveat: str = CAVEAT


class ThinCoverageNote(BaseModel):
    ku_id: str
    label: str


class DiscoverResponse(BaseModel):
    resolved_kus: list[KULabel]
    courses: list[CourseResult]
    combinations: list[CombinationResult]
    thin_coverage: list[ThinCoverageNote]
    status: Literal["ok", "no_concepts_resolved", "no_courses_found"]
    status_message: Optional[str] = None


# --- Readiness (REQ-AQ-09) ---------------------------------------------------

class ReadinessRequest(BaseModel):
    course_id: str = Field(..., min_length=1)
    # Session-scoped only; never persisted.
    completed_courses: list[str] = Field(default_factory=list)


class UnmetPrerequisite(BaseModel):
    course_id: str
    title: str
    verbatim: str  # catalogue's verbatim wording, "" if unavailable


class ReadinessResponse(BaseModel):
    course_id: str
    ready: bool
    unmet_prerequisites: list[UnmetPrerequisite]
    evidence_basis: Literal["declared"] = "declared"
    status: Literal["ok", "course_not_found"] = "ok"
    status_message: Optional[str] = None


# --- Unlock (REQ-AQ-10) ------------------------------------------------------

class UnlockedCourse(BaseModel):
    course_id: str
    title: str


class UnlockResponse(BaseModel):
    course_id: str
    unlocks: list[UnlockedCourse]
    evidence_basis: Literal["declared"] = "declared"
    status: Literal["ok", "course_not_found"] = "ok"
    status_message: Optional[str] = None


# --- Course detail -----------------------------------------------------------

class CourseConcept(BaseModel):
    ku_id: str
    label: str
    knowledge_area: str
    confidence: float


class CoursePrerequisite(BaseModel):
    course_id: str
    title: str
    verbatim: str


class CourseDetailResponse(BaseModel):
    course_id: str
    course_number: str
    subject_code: str
    title: str
    level: str
    description: str
    concepts: list[CourseConcept]          # covered CS2023 knowledge units
    prerequisites: list[CoursePrerequisite]  # declared
    unlocks: list[UnlockedCourse]          # declared, transitive
    evidence_basis: Literal["mixed"] = "mixed"  # description declared; concepts inferred
    status: Literal["ok", "course_not_found"] = "ok"
    status_message: Optional[str] = None


# --- Overlap (REQ-AQ-08) -----------------------------------------------------

OVERLAP_CAVEAT = (
    "Overlap is inferred from course descriptions via the CS2023 vocabulary "
    "and may not reflect actual course content; it does not imply exemption."
)


class OverlapConcept(BaseModel):
    ku_id: str
    label: str
    knowledge_area: str


class OverlapRequest(BaseModel):
    course_id: str = Field(..., min_length=1)
    # Session-scoped only; never persisted.
    completed_courses: list[str] = Field(default_factory=list)


class OverlapResponse(BaseModel):
    course_id: str
    matched_concepts: list[OverlapConcept]   # target KUs already covered
    gap_concepts: list[OverlapConcept]       # target KUs not covered
    confidence: float                        # mean alignment confidence over matched KUs
    evidence_basis: Literal["inferred"] = "inferred"
    caveat: str = OVERLAP_CAVEAT
    status: Literal["ok", "course_not_found"] = "ok"
    status_message: Optional[str] = None
