"""AcalogCatalogueAdapter — discovers course and programme URLs from catalog.purdue.edu."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup

from granular.ingestion.http_client import FetchFailure, RateLimitedClient
from granular.ingestion.robots import RobotsCache

logger = logging.getLogger(__name__)

_CATOID_RE = re.compile(r"catoid=(\d+)")
_COID_RE = re.compile(r"coid=(\d+)")


@dataclass
class CourseUrl:
    catoid: str
    coid: str
    url: str


@dataclass
class ProgrammeUrl:
    catoid: str
    navoid: str
    url: str


class AcalogCatalogueAdapter:
    """Discovers course and programme URLs by walking the Acalog index pages.

    The current catoid is discovered dynamically from the catalogue index,
    so the adapter survives a catalogue year rollover.
    """

    def __init__(
        self,
        base_url: str,
        subject_filter: str,
        client: RateLimitedClient,
        robots: RobotsCache,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._subject = subject_filter
        self._client = client
        self._robots = robots

    def _fetch(self, url: str) -> Optional[str]:
        """Fetch a URL respecting robots.txt. Returns body or None on failure."""
        if not self._robots.is_allowed(url):
            logger.info("robots_disallowed: %s", url)
            return None
        result = self._client.get(url)
        if isinstance(result, FetchFailure):
            logger.warning("Fetch failed for %s: %s", url, result.reason)
            return None
        return result.body

    def discover_catoid(self) -> Optional[str]:
        """Discover the current catalogue year's catoid from the index page."""
        index_url = f"{self._base}/index.php"
        body = self._fetch(index_url)
        if not body:
            # Try without index.php
            body = self._fetch(f"{self._base}/")
        if not body:
            return None

        soup = BeautifulSoup(body, "html.parser")
        # Look for links containing catoid=N — take the highest number as current
        catoids: list[int] = []
        for a in soup.find_all("a", href=True):
            m = _CATOID_RE.search(a["href"])
            if m:
                catoids.append(int(m.group(1)))

        if not catoids:
            logger.warning("Could not discover catoid from %s", index_url)
            return None

        catoid = str(max(catoids))
        logger.info("Discovered catoid=%s", catoid)
        return catoid

    def discover_course_urls(self, catoid: str) -> list[CourseUrl]:
        """Discover all CS course URLs for the given catoid.

        Walks paginated course list pages.
        """
        urls: list[CourseUrl] = []
        page = 1

        while True:
            list_url = (
                f"{self._base}/content.php"
                f"?catoid={catoid}"
                f"&filter%5B3%5D={self._subject}"
                f"&filter%5Bitem_type%5D=3"
                f"&filter%5Bonly_active%5D=1"
                f"&filter%5Bcpage%5D={page}"
                f"&navoid={catoid}"
            )
            body = self._fetch(list_url)
            if not body:
                break

            soup = BeautifulSoup(body, "html.parser")
            found_on_page = 0
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "preview_course_nopop.php" in href:
                    cat_m = _CATOID_RE.search(href)
                    coid_m = _COID_RE.search(href)
                    if cat_m and coid_m:
                        full_url = f"{self._base}/{href.lstrip('/')}"
                        urls.append(
                            CourseUrl(
                                catoid=cat_m.group(1),
                                coid=coid_m.group(1),
                                url=full_url,
                            )
                        )
                        found_on_page += 1

            logger.debug("Page %d: found %d course links", page, found_on_page)

            # Check for "next page" link
            next_link = soup.find("a", string=re.compile(r"Next", re.IGNORECASE))
            if not next_link or found_on_page == 0:
                break
            page += 1

        logger.info("Discovered %d course URLs (catoid=%s)", len(urls), catoid)
        return urls

    def discover_programme_urls(self, catoid: str) -> list[ProgrammeUrl]:
        """Discover CS programme page URLs for the given catoid."""
        urls: list[ProgrammeUrl] = []
        list_url = (
            f"{self._base}/content.php"
            f"?catoid={catoid}"
            f"&filter%5Bitem_type%5D=1"
            f"&filter%5Bonly_active%5D=1"
            f"&navoid={catoid}"
        )
        body = self._fetch(list_url)
        if not body:
            return urls

        soup = BeautifulSoup(body, "html.parser")
        cs_keywords = re.compile(r"computer\s+science|cs\b", re.IGNORECASE)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "content.php" in href and "navoid" in href:
                link_text = a.get_text(strip=True)
                if cs_keywords.search(link_text):
                    navoid_m = re.search(r"navoid=(\d+)", href)
                    cat_m = _CATOID_RE.search(href)
                    if navoid_m and cat_m:
                        full_url = f"{self._base}/{href.lstrip('/')}"
                        urls.append(
                            ProgrammeUrl(
                                catoid=cat_m.group(1),
                                navoid=navoid_m.group(1),
                                url=full_url,
                            )
                        )

        logger.info("Discovered %d CS programme URLs", len(urls))
        return urls
