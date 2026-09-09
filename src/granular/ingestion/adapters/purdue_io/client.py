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

        Raises ODataUnavailable on HTTP error or timeout.
        """
        url = (
            f"{self._base}/Courses"
            f"?$filter=Subject eq '{self._subject}'"
            f"&$select=CourseID,Subject,Number,Title,Description,CreditHours"
            f"&$top=500"
        )
        try:
            response = httpx.get(url, timeout=self._timeout)
            response.raise_for_status()
            data = response.json()
            courses = []
            for item in data.get("value", []):
                try:
                    courses.append(
                        ODataCourse(
                            course_id=str(item.get("CourseID", "")),
                            subject=item.get("Subject", ""),
                            number=str(item.get("Number", "")),
                            title=item.get("Title", ""),
                            description=item.get("Description", "") or "",
                            credit_hours=float(item["CreditHours"]) if item.get("CreditHours") else None,
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
