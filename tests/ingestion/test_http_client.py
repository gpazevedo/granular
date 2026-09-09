"""Tests for RateLimitedClient (network-free)."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from granular.ingestion.http_client import FetchFailure, FetchResult, RateLimitedClient


@pytest.fixture
def tmp_cache(tmp_path):
    return tmp_path / "test_cache.db"


class TestRateLimitedClient:
    def test_constructs_and_closes(self, tmp_cache):
        client = RateLimitedClient(
            user_agent="TestBot/1.0",
            requests_per_second=10.0,
            cache_db_path=tmp_cache,
        )
        client.close()

    def test_context_manager(self, tmp_cache):
        with RateLimitedClient(
            user_agent="TestBot/1.0",
            requests_per_second=10.0,
            cache_db_path=tmp_cache,
        ) as client:
            assert client is not None

    def test_cache_db_created(self, tmp_cache):
        with RateLimitedClient(
            user_agent="TestBot/1.0",
            requests_per_second=10.0,
            cache_db_path=tmp_cache,
        ):
            pass
        assert tmp_cache.exists()

    def test_token_bucket_rate_limiting(self, tmp_cache):
        """Token bucket should enforce delay between requests."""
        client = RateLimitedClient(
            user_agent="TestBot/1.0",
            requests_per_second=2.0,  # 2 req/s → 0.5s between requests
            cache_db_path=tmp_cache,
        )
        start = time.monotonic()
        client._acquire_token()
        client._acquire_token()
        elapsed = time.monotonic() - start
        client.close()
        # Second token should have caused at least ~0.4s delay
        assert elapsed >= 0.4
