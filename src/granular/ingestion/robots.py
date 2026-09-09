"""RobotsCache — fetch, parse, and check robots.txt for the catalogue."""

from __future__ import annotations

import logging
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger(__name__)


class RobotsCache:
    """Fetches robots.txt once at startup and caches it for the run."""

    def __init__(self, base_url: str, user_agent: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent
        self._parser = RobotFileParser()
        self._loaded = False

    def load(self) -> None:
        """Fetch and parse robots.txt. Call once before any requests."""
        robots_url = f"{self._base_url}/robots.txt"
        try:
            response = httpx.get(robots_url, timeout=10, follow_redirects=True)
            self._parser.set_url(robots_url)
            self._parser.parse(response.text.splitlines())
            self._loaded = True
            logger.info("robots.txt loaded from %s", robots_url)
        except Exception as exc:
            # If robots.txt is unreachable, assume all paths are allowed
            # (fail-open for research artefact; log prominently).
            logger.warning(
                "Could not fetch robots.txt from %s (%s). "
                "Assuming all paths are allowed.",
                robots_url,
                exc,
            )
            self._loaded = True  # mark loaded so is_allowed works

    def is_allowed(self, url: str) -> bool:
        """Return True if the URL is allowed to be fetched."""
        if not self._loaded:
            raise RuntimeError("RobotsCache.load() must be called before is_allowed()")
        return self._parser.can_fetch(self._user_agent, url)
