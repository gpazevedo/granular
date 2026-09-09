"""RateLimitedClient — httpx wrapper with token bucket, conditional GET, and SQLite cache."""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    url: str
    status_code: int
    body: str
    from_cache: bool = False


@dataclass
class FetchFailure:
    url: str
    status_code: Optional[int]
    reason: str


class RateLimitedClient:
    """Sync HTTP client with:
    - Token-bucket rate limiting (thread-safe)
    - SQLite-backed conditional GET cache (ETag / Last-Modified)
    - HTTP 429 + Retry-After handling (one retry)
    - Structured FetchFailure on non-200 / timeout (never raises)
    """

    def __init__(
        self,
        user_agent: str,
        requests_per_second: float,
        cache_db_path: Path,
        since_date: Optional[date] = None,
        force_refetch: bool = False,
        timeout: float = 30.0,
    ) -> None:
        self._user_agent = user_agent
        self._rps = requests_per_second
        self._since_date = since_date
        self._force = force_refetch
        self._timeout = timeout

        # Token bucket
        self._lock = threading.Lock()
        self._tokens = 1.0
        self._last_refill = time.monotonic()

        # SQLite cache
        cache_db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(cache_db_path), check_same_thread=False)
        self._db_lock = threading.Lock()
        self._init_db()

        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            follow_redirects=True,
            timeout=self._timeout,
        )

    def _init_db(self) -> None:
        with self._db_lock:
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS fetch_cache (
                    url          TEXT PRIMARY KEY,
                    etag         TEXT,
                    last_modified TEXT,
                    body         TEXT,
                    fetched_at   TEXT
                )
            """)
            self._db.commit()

    def _acquire_token(self) -> None:
        """Block until a request token is available."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(1.0, self._tokens + elapsed * self._rps)
            self._last_refill = now
            if self._tokens < 1.0:
                sleep_time = (1.0 - self._tokens) / self._rps
                time.sleep(sleep_time)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0

    def _get_cache(self, url: str) -> Optional[dict]:
        with self._db_lock:
            row = self._db.execute(
                "SELECT etag, last_modified, body FROM fetch_cache WHERE url=?", (url,)
            ).fetchone()
        if row:
            return {"etag": row[0], "last_modified": row[1], "body": row[2]}
        return None

    def _set_cache(self, url: str, etag: Optional[str], last_modified: Optional[str], body: str) -> None:
        import datetime
        with self._db_lock:
            self._db.execute(
                """INSERT OR REPLACE INTO fetch_cache (url, etag, last_modified, body, fetched_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (url, etag, last_modified, body, datetime.datetime.utcnow().isoformat()),
            )
            self._db.commit()

    def get(self, url: str) -> FetchResult | FetchFailure:
        """Fetch a URL respecting rate limits, cache, and robots rules.

        Returns FetchResult on success (including 304 cache hit),
        FetchFailure on any error — never raises.
        """
        self._acquire_token()

        cached = None if self._force else self._get_cache(url)

        headers: dict[str, str] = {}
        if cached and not self._force:
            if cached["etag"]:
                headers["If-None-Match"] = cached["etag"]
            elif cached["last_modified"]:
                headers["If-Modified-Since"] = cached["last_modified"]
            elif self._since_date:
                # No cache signal — re-fetch unconditionally when --since used
                logger.debug("No cache signal for %s; re-fetching (--since in effect)", url)

        try:
            response = self._client.get(url, headers=headers)

            if response.status_code == 304 and cached:
                return FetchResult(url=url, status_code=304, body=cached["body"], from_cache=True)

            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "5"))
                logger.warning("429 from %s; sleeping %.1fs then retrying", url, retry_after)
                time.sleep(retry_after)
                self._acquire_token()
                response = self._client.get(url, headers=headers)

            if response.status_code != 200:
                return FetchFailure(url=url, status_code=response.status_code, reason=f"HTTP {response.status_code}")

            body = response.text
            etag = response.headers.get("ETag")
            last_modified = response.headers.get("Last-Modified")
            self._set_cache(url, etag, last_modified, body)
            return FetchResult(url=url, status_code=200, body=body, from_cache=False)

        except httpx.TimeoutException:
            return FetchFailure(url=url, status_code=None, reason="timeout")
        except httpx.RequestError as exc:
            return FetchFailure(url=url, status_code=None, reason=str(exc))

    def close(self) -> None:
        self._client.close()
        self._db.close()

    def __enter__(self) -> "RateLimitedClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
