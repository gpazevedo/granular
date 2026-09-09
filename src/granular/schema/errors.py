"""Structured validation errors for the canonical schema."""

from __future__ import annotations

from typing import Any


class SchemaValidationError(Exception):
    """Raised when a schema object fails construction-time validation.

    Never swallowed. Always propagates to the caller.
    """

    def __init__(
        self,
        record_type: str,
        field_name: str,
        value: Any,
        reason: str,
    ) -> None:
        self.record_type = record_type
        self.field_name = field_name
        self.value = value
        self.reason = reason
        super().__init__(
            f"[{record_type}.{field_name}] {reason} (got {value!r})"
        )
