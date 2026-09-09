"""Tests for the ingestion snapshot module (Option A — reusable dataset)."""

from __future__ import annotations

import json

import pytest

from granular.ingestion.snapshot import (
    create_snapshot,
    resolve_courses_path,
    verify_snapshot,
)


def _write_output(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "courses.jsonl").write_text(
        '{"course_id": "CS-18000"}\n{"course_id": "CS-25100"}\n', encoding="utf-8"
    )
    (output_dir / "edges.jsonl").write_text('{"edge_id": "e1"}\n', encoding="utf-8")
    (output_dir / "programmes.jsonl").write_text('{"programme_id": "p1"}\n', encoding="utf-8")
    (output_dir / "summary.json").write_text('{"courses_succeeded": 2}', encoding="utf-8")


class TestCreateSnapshot:
    def test_creates_snapshot_with_manifest(self, tmp_path):
        output_dir = tmp_path / "output"
        snapshot_root = tmp_path / "snapshots"
        _write_output(output_dir)

        snap_dir = create_snapshot(output_dir, snapshot_root, "purdue-2026-2027", "2026-2027")

        assert (snap_dir / "courses.jsonl").exists()
        assert (snap_dir / "edges.jsonl").exists()
        assert (snap_dir / "programmes.jsonl").exists()
        manifest = json.loads((snap_dir / "manifest.json").read_text())
        assert manifest["name"] == "purdue-2026-2027"
        assert manifest["catalogue_year"] == "2026-2027"
        assert manifest["files"]["courses.jsonl"]["records"] == 2

    def test_missing_output_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            create_snapshot(tmp_path / "nope", tmp_path / "snap", "x")


class TestResolveCoursesPath:
    def test_resolves_existing(self, tmp_path):
        output_dir = tmp_path / "output"
        snapshot_root = tmp_path / "snapshots"
        _write_output(output_dir)
        create_snapshot(output_dir, snapshot_root, "snap1")
        path = resolve_courses_path(snapshot_root, "snap1")
        assert path.exists()

    def test_missing_snapshot_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            resolve_courses_path(tmp_path, "does-not-exist")


class TestVerifySnapshot:
    def test_verify_passes_for_intact_snapshot(self, tmp_path):
        output_dir = tmp_path / "output"
        snapshot_root = tmp_path / "snapshots"
        _write_output(output_dir)
        create_snapshot(output_dir, snapshot_root, "snap1")
        assert verify_snapshot(snapshot_root, "snap1") is True

    def test_verify_fails_on_tamper(self, tmp_path):
        output_dir = tmp_path / "output"
        snapshot_root = tmp_path / "snapshots"
        _write_output(output_dir)
        create_snapshot(output_dir, snapshot_root, "snap1")
        # Tamper with a file after snapshot
        (snapshot_root / "snap1" / "courses.jsonl").write_text("tampered\n", encoding="utf-8")
        assert verify_snapshot(snapshot_root, "snap1") is False

    def test_verify_missing_manifest(self, tmp_path):
        assert verify_snapshot(tmp_path, "nope") is False
