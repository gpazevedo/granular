"""Tests for EvalConfig and ArtefactStore (Tasks 1, 2)."""

from __future__ import annotations

import json

import pytest

from granular.evaluation.artefacts import ArtefactStore
from granular.evaluation.config import EvalConfig


class TestEvalConfig:
    def test_valid_defaults(self):
        cfg = EvalConfig()
        assert cfg.held_out_fraction == 0.20
        assert cfg.random_seed == 42

    def test_rejects_bad_fraction(self):
        with pytest.raises(ValueError):
            EvalConfig(held_out_fraction=1.5)

    def test_rejects_negative_seed(self):
        with pytest.raises(ValueError):
            EvalConfig(random_seed=-1)

    def test_rejects_inverted_confidence_bands(self):
        with pytest.raises(ValueError):
            EvalConfig(confidence_high=0.3, confidence_medium_low=0.5)

    def test_confidence_band(self):
        cfg = EvalConfig()
        assert cfg.confidence_band(0.8) == "high"
        assert cfg.confidence_band(0.5) == "medium"
        assert cfg.confidence_band(0.2) == "low"


class TestArtefactStore:
    def test_init_run_creates_dir(self, tmp_path):
        store = ArtefactStore(tmp_path)
        run_dir = store.init_run("run-1")
        assert run_dir.exists()

    def test_init_run_rejects_existing(self, tmp_path):
        store = ArtefactStore(tmp_path)
        store.init_run("run-1")
        store2 = ArtefactStore(tmp_path)
        with pytest.raises(RuntimeError):
            store2.init_run("run-1")

    def test_write_json_and_manifest(self, tmp_path):
        store = ArtefactStore(tmp_path)
        store.init_run("run-1")
        store.write("split", {"train": [1, 2], "test": [3]})
        store.write("report_md", "# Report\n")
        manifest_path = store.finalise_manifest()

        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["run_id"] == "run-1"
        assert len(manifest["artefacts"]) == 2
        # Every artefact has a checksum
        for entry in manifest["artefacts"]:
            assert "sha256" in entry
            assert len(entry["sha256"]) == 64

    def test_filenames_prefixed_with_run_id(self, tmp_path):
        store = ArtefactStore(tmp_path)
        store.init_run("run-42")
        path = store.write("split", {"x": 1})
        assert path.name.startswith("run-42_")
