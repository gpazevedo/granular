"""Map OData records to cross-check fields against HTML-parsed RawCourse data."""

from __future__ import annotations

import logging
from typing import Optional

from granular.ingestion.adapters.purdue_io.client import ODataCourse

logger = logging.getLogger(__name__)


def cross_check(
    html_description: str,
    odata_course: Optional[ODataCourse],
    source_url: str,
) -> str:
    """Return the authoritative description (always HTML) and log discrepancies.

    OData is secondary — used only for cross-checking, never to override HTML.
    """
    if odata_course is None or not odata_course.description:
        return html_description

    if odata_course.description.strip() != html_description.strip():
        logger.info(
            "OData/HTML description mismatch for %s\n"
            "  HTML:  %.80s…\n"
            "  OData: %.80s…",
            source_url,
            html_description,
            odata_course.description,
        )

    # HTML wins regardless
    return html_description
