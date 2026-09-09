"""ProvenanceRecord — carried by every schema object."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from granular.schema.errors import SchemaValidationError


@dataclass
class ProvenanceRecord:
    """Origin metadata required on every schema record.

    Invariant: every field is validated at construction time.
    source_revision is optional (None when the source does not state one).
    """

    source_url: str
    retrieved_at: datetime          # must be timezone-aware UTC
    adapter_name: str
    adapter_version: str            # semver string, e.g. "1.0.0"
    source_revision: Optional[str]  # catalogue year / edition, or None

    def __post_init__(self) -> None:
        _require_nonempty(self, "source_url", self.source_url)
        if not self.source_url.startswith("http"):
            raise SchemaValidationError(
                "ProvenanceRecord",
                "source_url",
                self.source_url,
                "must start with 'http'",
            )
        if self.retrieved_at.tzinfo is None:
            raise SchemaValidationError(
                "ProvenanceRecord",
                "retrieved_at",
                self.retrieved_at,
                "must be timezone-aware (UTC)",
            )
        _require_nonempty(self, "adapter_name", self.adapter_name)
        _require_nonempty(self, "adapter_version", self.adapter_version)

    @classmethod
    def now(
        cls,
        source_url: str,
        adapter_name: str,
        adapter_version: str,
        source_revision: Optional[str] = None,
    ) -> "ProvenanceRecord":
        """Convenience constructor with current UTC time."""
        return cls(
            source_url=source_url,
            retrieved_at=datetime.now(tz=timezone.utc),
            adapter_name=adapter_name,
            adapter_version=adapter_version,
            source_revision=source_revision,
        )


def _require_nonempty(obj: object, field: str, value: str) -> None:
    if not value or not value.strip():
        raise SchemaValidationError(
            type(obj).__name__,
            field,
            value,
            "must be a non-empty string",
        )
