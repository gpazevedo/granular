"""EntitlementLanguageGuard — hard failure on entitlement language in responses."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


class EntitlementLanguageError(Exception):
    """Raised when a response field contains entitlement language."""

    def __init__(self, text: str, matched_pattern: str) -> None:
        self.text = text
        self.matched_pattern = matched_pattern
        super().__init__(
            f"Entitlement language detected (pattern {matched_pattern!r}): {text[:80]!r}"
        )


@dataclass
class GuardResult:
    clean: bool
    matched_pattern: Optional[str] = None


class EntitlementLanguageGuard:
    """Scans text for forbidden entitlement phrases. Case-insensitive."""

    def __init__(self, patterns: list[str]) -> None:
        self._compiled = [re.compile(p, re.IGNORECASE) for p in patterns]

    def check(self, text: str) -> GuardResult:
        for pattern in self._compiled:
            if pattern.search(text):
                return GuardResult(clean=False, matched_pattern=pattern.pattern)
        return GuardResult(clean=True)

    def assert_clean(self, text: str) -> None:
        """Raise EntitlementLanguageError if text contains entitlement language."""
        result = self.check(text)
        if not result.clean:
            raise EntitlementLanguageError(text, result.matched_pattern or "")
