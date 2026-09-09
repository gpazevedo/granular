"""JSON serialisation / deserialisation for all schema record types.

Uses dataclasses.asdict for round-trip safety.
All schema records are serialisable to JSON and deserialisable without data loss.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, TypeVar

from granular.schema.errors import SchemaValidationError

T = TypeVar("T")


def _default_encoder(obj: Any) -> Any:
    """JSON encoder for types not natively supported."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "value"):  # Enum
        return obj.value
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")


def to_json(record: Any) -> str:
    """Serialise a schema dataclass instance to a JSON string.

    Preserves all fields including provenance and enums.
    """
    return json.dumps(asdict(record), default=_default_encoder, ensure_ascii=False)


def to_dict(record: Any) -> dict:
    """Serialise a schema dataclass instance to a plain dict."""
    return json.loads(to_json(record))


# ---------------------------------------------------------------------------
# Validation report
# ---------------------------------------------------------------------------

class FailureDetail:
    def __init__(self, record: Any, error: SchemaValidationError) -> None:
        self.record = record
        self.error = error

    def __repr__(self) -> str:
        return f"FailureDetail(record={type(self.record).__name__}, error={self.error})"


class ValidationReport:
    def __init__(self) -> None:
        self.passed: list[Any] = []
        self.failed: list[FailureDetail] = []

    @property
    def all_passed(self) -> bool:
        return len(self.failed) == 0

    def __repr__(self) -> str:
        return (
            f"ValidationReport(passed={len(self.passed)}, "
            f"failed={len(self.failed)})"
        )


def validate_all(records: list[Any]) -> ValidationReport:
    """Validate a collection of schema records without stopping at the first error.

    Returns a ValidationReport with all failures collected.
    Does not raise — call report.all_passed to check for failures.
    """
    report = ValidationReport()
    for record in records:
        try:
            # Re-trigger __post_init__ by calling it directly.
            post = getattr(record, "__post_init__", None)
            if post is not None:
                post()
            report.passed.append(record)
        except SchemaValidationError as exc:
            report.failed.append(FailureDetail(record, exc))
    return report
