"""PurdueIoClient — OData v4 client for api.purdue.io."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class ODataUnavailable(Exception):
    """Raised when the purdue.io OData API is not reachable."""


@dataclass
class ODataCourse:
    course_id: str
    subject: str
    number: str
    title: str
    description: str
    credit_hours: Optional[float]


class PurdueIoClient:
    """Queries the community purdue.io OData API.

    Used only for cross-checking HTML-parsed data.
    HTML is always authoritative when values conflict.
    """

    def __init__(self, base_url: str, subject_filter: str, timeout: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._subject = subject_filter
        self._timeout = timeout

    def fetch_all(self) -> list[ODataCourse]:
        """Fetch all courses for the configured subject.

        Uses a navigation-property filter (Subject/Abbreviation eq 'CS'). The
        server caps $top at 0, so no $top is sent; the filtered collection
        returns in full. Raises ODataUnavailable on HTTP error or timeout.
        """
        url = f"{self._base}/Courses"
        params = {"$filter": f"Subject/Abbreviation eq '{self._subject}'"}
        try:
            response = httpx.get(url, params=params, timeout=self._timeout)
            response.raise_for_status()
            data = response.json()
            courses = []
            for item in data.get("value", []):
                try:
                    courses.append(
                        ODataCourse(
                            course_id=str(item.get("Id", "")),
                            subject=self._subject,
                            number=str(item.get("Number", "")),
                            title=item.get("Title", ""),
                            description=item.get("Description", "") or "",
                            credit_hours=float(item["CreditHours"]) if item.get("CreditHours") is not None else None,
                        )
                    )
                except (KeyError, ValueError, TypeError) as exc:
                    logger.debug("Skipping malformed OData record: %s", exc)
            logger.info("purdue.io OData: fetched %d courses", len(courses))
            return courses
        except httpx.HTTPStatusError as exc:
            raise ODataUnavailable(f"HTTP {exc.response.status_code}") from exc
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise ODataUnavailable(str(exc)) from exc
