"""Tests for the EntitlementLanguageGuard."""

from __future__ import annotations

import pytest

from granular.api.config import APIConfig
from granular.api.guards.language_guard import (
    EntitlementLanguageError,
    EntitlementLanguageGuard,
)


def make_guard() -> EntitlementLanguageGuard:
    return EntitlementLanguageGuard(APIConfig().entitlement_patterns)


class TestEntitlementLanguageGuard:
    def test_clean_text_passes(self):
        guard = make_guard()
        assert guard.check("This course covers binary trees and sorting.").clean

    def test_exempt_flagged(self):
        guard = make_guard()
        result = guard.check("You are exempt from this requirement.")
        assert not result.clean

    def test_covers_everything_flagged(self):
        guard = make_guard()
        assert not guard.check("This course covers everything you need.").clean

    def test_you_can_skip_flagged(self):
        guard = make_guard()
        assert not guard.check("You can skip the intro course.").clean

    def test_assert_clean_raises(self):
        guard = make_guard()
        with pytest.raises(EntitlementLanguageError):
            guard.assert_clean("You will master all of algorithms.")

    def test_case_insensitive(self):
        guard = make_guard()
        assert not guard.check("EXEMPT from prerequisites").clean
