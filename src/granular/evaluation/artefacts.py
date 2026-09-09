"""ArtefactStore — versioned file management with checksum manifest. (Task 2)"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class ArtefactStore:
    """Manages versioned evaluation artefacts and produces a checksum manifest."""

    def __init__(self, artefact_dir: Path) -> None:
        self._artefact_dir = Path(artefact_dir)
        self._run_dir: Path | None = None
        self._run_id: str | None = None
        self._manifest: list[dict] = []

    def init_run(self, run_id: str, resume: bool = False) -> Path:
        """Create the run directory. Raises if it exists unless resume=True."""
        self._run_id = run_id
        self._run_dir = self._artefact_dir / run_id
        if self._run_dir.exists() and not resume:
            raise RuntimeError(f"Run directory already exists: {self._run_dir}")
        self._run_dir.mkdir(parents=True, exist_ok=True)
        return self._run_dir

    def write(self, name: str, data: dict | str) -> Path:
        """Write a JSON (dict) or Markdown (str) artefact to the run directory."""
        if self._run_dir is None or self._run_id is None:
            raise RuntimeError("init_run() must be called before write()")

        if isinstance(data, dict):
            filename = f"{self._run_id}_{name}.json"
            path = self._run_dir / filename
            path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        else:
            filename = f"{self._run_id}_{name}.md"
            path = self._run_dir / filename
            path.write_text(data, encoding="utf-8")

        self._manifest.append(
            {"filename": filename, "written_at": datetime.now(tz=timezone.utc).isoformat()}
        )
        return path

    def finalise_manifest(self) -> Path:
        """Compute checksums for all written artefacts and write manifest.json."""
        if self._run_dir is None or self._run_id is None:
            raise RuntimeError("init_run() must be called before finalise_manifest()")

        for entry in self._manifest:
            file_path = self._run_dir / entry["filename"]
            if file_path.exists():
                entry["sha256"] = _sha256(file_path)

        manifest_path = self._run_dir / f"{self._run_id}_manifest.json"
        manifest_path.write_text(
            json.dumps({"run_id": self._run_id, "artefacts": self._manifest}, indent=2),
            encoding="utf-8",
        )
        return manifest_path

    @property
    def run_dir(self) -> Path:
        if self._run_dir is None:
            raise RuntimeError("init_run() not called")
        return self._run_dir


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
