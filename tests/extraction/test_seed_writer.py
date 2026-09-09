"""Tests for the CS2023 seed writer/loader (network-free)."""

from __future__ import annotations

import json

from granular.extraction.bootstrap.pdf_parser import ParsedKU
from granular.extraction.bootstrap.seed_writer import (
    build_knowledge_units,
    load_seed,
    write_seed,
)
from granular.schema import KnowledgeTier


def make_parsed() -> list[ParsedKU]:
    return [
        ParsedKU(ku_id="CS2023-AL-KU-1", label="Basic Analysis", knowledge_area_code="AL", tier="core", contact_hours=5.0),
        ParsedKU(ku_id="CS2023-IS-KU-1", label="Machine Learning", knowledge_area_code="IS", tier="elective", contact_hours=10.0),
    ]


class TestSeedWriter:
    def test_build_knowledge_units(self):
        units = build_knowledge_units(make_parsed())
        assert len(units) == 2
        assert units[0].tier == KnowledgeTier.CORE
        assert units[1].tier == KnowledgeTier.ELECTIVE

    def test_write_and_load_round_trip(self, tmp_path):
        units = build_knowledge_units(make_parsed())
        seed_path = tmp_path / "vocab.json"
        write_seed(units, seed_path)

        assert seed_path.exists()
        data = json.loads(seed_path.read_text())
        assert data["source"] == "CS2023"
        assert data["knowledge_unit_count"] == 2
        assert data["knowledge_area_count"] == 2

        loaded = load_seed(seed_path)
        assert len(loaded) == 2
        assert {u.ku_id for u in loaded} == {"CS2023-AL-KU-1", "CS2023-IS-KU-1"}

    def test_loaded_units_are_valid_schema(self, tmp_path):
        units = build_knowledge_units(make_parsed())
        seed_path = tmp_path / "vocab.json"
        write_seed(units, seed_path)
        loaded = load_seed(seed_path)
        for ku in loaded:
            assert ku.source == "CS2023"
            assert ku.knowledge_area in ("AL", "IS")
