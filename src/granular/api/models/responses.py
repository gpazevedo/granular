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
