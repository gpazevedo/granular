"""Snapshot management — promote a one-time ingestion run into a committed,
reusable dataset so Purdue is fetched only once.

Option A from the reuse decision: the parsed canonical-schema JSONL files
(courses, edges, programmes) plus the run summary are copied into a versioned
snapshot directory under `data/snapshots/<name>/`, which IS committed to the
repository (the gitignore excludes `data/ingestion/output/` but not
`data/snapshots/`).

Downstream stages (concept-extraction, evaluation) read from the snapshot,
never from the network.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ARTEFACTS = ("courses.jsonl", "edges.jsonl", "programmes.jsonl", "summary.json")


@dataclass
class SnapshotManifest:
    name: str
    created_at: str
    catalogue_year: Optional[str]
    source_run_summary: Optional[str]
    files: dict[str, dict]  # filename -> {sha256, records}

    def to_dict(self) -> dict:
        return asdict(self)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def create_snapshot(
    output_dir: Path,
    snapshot_root: Path,
    name: str,
    catalogue_year: Optional[str] = None,
) -> Path:
    """Promote an ingestion output directory into a committed snapshot.

    Copies the JSONL artefacts + summary into `snapshot_root/<name>/` and writes
    a manifest with checksums and record counts. Returns the snapshot directory.

    Raises FileNotFoundError if the required course artefact is missing.
    """
    output_dir = Path(output_dir)
    snapshot_dir = Path(snapshot_root) / name

    courses_path = output_dir / "courses.jsonl"
    if not courses_path.exists():
        raise FileNotFoundError(
            f"No ingestion output found at {courses_path}. Run 'granular-ingest run' first."
        )

    snapshot_dir.mkdir(parents=True, exist_ok=True)

    files: dict[str, dict] = {}
    for artefact in _ARTEFACTS:
        src = output_dir / artefact
        if not src.exists():
            logger.warning("Snapshot: artefact %s not found in output; skipping", artefact)
            continue
        dst = snapshot_dir / artefact
        shutil.copy2(src, dst)
        files[artefact] = {
            "sha256": _sha256(dst),
            "records": _count_lines(dst) if artefact.endswith(".jsonl") else None,
        }

    manifest = SnapshotManifest(
        name=name,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
        catalogue_year=catalogue_year,
        source_run_summary=str(output_dir / "summary.json"),
        files=files,
    )
    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")

    logger.info(
        "Snapshot '%s' created at %s (%d artefacts)",
        name,
        snapshot_dir,
        len(files),
    )
    return snapshot_dir


def resolve_courses_path(
    snapshot_root: Path,
    name: str,
) -> Path:
    """Return the courses.jsonl path inside a named snapshot.

    Raises FileNotFoundError if the snapshot or its courses file is missing.
    """
    courses_path = Path(snapshot_root) / name / "courses.jsonl"
    if not courses_path.exists():
        raise FileNotFoundError(
            f"Snapshot '{name}' has no courses.jsonl at {courses_path}"
        )
    return courses_path


def verify_snapshot(snapshot_root: Path, name: str) -> bool:
    """Verify a snapshot's artefacts match the checksums in its manifest.

    Returns True if all present files match; logs and returns False otherwise.
    """
    snapshot_dir = Path(snapshot_root) / name
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        logger.error("No manifest at %s", manifest_path)
        return False

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ok = True
    for filename, meta in manifest.get("files", {}).items():
        path = snapshot_dir / filename
        if not path.exists():
            logger.error("Snapshot file missing: %s", path)
            ok = False
            continue
        actual = _sha256(path)
        if actual != meta.get("sha256"):
            logger.error("Checksum mismatch for %s", filename)
            ok = False
    return ok
