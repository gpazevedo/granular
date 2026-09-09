"""POST /api/v1/discover — interest-driven discovery endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from granular.api.dependencies import get_discover_service
from granular.api.guards.language_guard import EntitlementLanguageError
from granular.api.models.responses import DiscoverRequest, DiscoverResponse
from granular.api.services.discover_service import DiscoverService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["discover"])


@router.post("/discover", response_model=DiscoverResponse)
def discover(
    request: DiscoverRequest,
    service: DiscoverService = Depends(get_discover_service),
) -> DiscoverResponse:
    """Resolve a plain-English interest to CS2023 knowledge units and return a
    prioritised course list plus course combinations.

    Returns HTTP 200 with a no_courses_found / no_concepts_resolved status body
    (not 404) when nothing matches. Returns HTTP 400 for an empty query.
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    try:
        return service.discover(request.query, request.level)
    except EntitlementLanguageError as exc:
        # Hard failure — surfaces a backend bug immediately rather than shipping
        # entitlement language to a student.
        logger.error("Entitlement language guard tripped: %s", exc)
        raise HTTPException(status_code=500, detail="Response failed content check") from exc
