"""Declared-layer advisory endpoints: readiness (REQ-AQ-09), unlock (REQ-AQ-10)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from granular.api.dependencies import get_advisory_service
from granular.api.models.responses import (
    CourseDetailResponse,
    OverlapRequest,
    OverlapResponse,
    ReadinessRequest,
    ReadinessResponse,
    UnlockResponse,
)
from granular.api.services.advisory_service import AdvisoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["advisory"])


@router.post("/readiness", response_model=ReadinessResponse)
def readiness(
    request: ReadinessRequest,
    service: AdvisoryService = Depends(get_advisory_service),
) -> ReadinessResponse:
    """Return the declared prerequisites for a course not met by the supplied
    completed-course list. Evidence basis: declared. The completed list is
    session-scoped and never persisted.

    HTTP 400 for an empty course_id; HTTP 200 with course_not_found otherwise.
    """
    if not request.course_id or not request.course_id.strip():
        raise HTTPException(status_code=400, detail="course_id must not be empty")
    return service.readiness(request.course_id.strip(), request.completed_courses)


@router.get("/unlock/{course_id}", response_model=UnlockResponse)
def unlock(
    course_id: str,
    service: AdvisoryService = Depends(get_advisory_service),
) -> UnlockResponse:
    """Return the courses a given course helps open up, via forward traversal
    over declared prerequisite edges only. Evidence basis: declared.
    """
    if not course_id or not course_id.strip():
        raise HTTPException(status_code=400, detail="course_id must not be empty")
    return service.unlock(course_id.strip())


@router.get("/course/{course_id}", response_model=CourseDetailResponse)
def course_detail(
    course_id: str,
    service: AdvisoryService = Depends(get_advisory_service),
) -> CourseDetailResponse:
    """Full detail for one course: description (declared), covered CS2023
    concepts (inferred), declared prerequisites, and what it unlocks.
    """
    if not course_id or not course_id.strip():
        raise HTTPException(status_code=400, detail="course_id must not be empty")
    return service.course_detail(course_id.strip())


@router.post("/overlap", response_model=OverlapResponse)
def overlap(
    request: OverlapRequest,
    service: AdvisoryService = Depends(get_advisory_service),
) -> OverlapResponse:
    """Return the target course's concepts already covered by the supplied
    completed courses (matched) and those not covered (gaps), at CS2023
    knowledge-unit grain. Evidence basis: inferred. The completed list is
    session-scoped and never persisted; the answer never implies exemption.
    """
    if not request.course_id or not request.course_id.strip():
        raise HTTPException(status_code=400, detail="course_id must not be empty")
    return service.overlap(request.course_id.strip(), request.completed_courses)
