"""Tests for CoverageIndex."""

from __future__ import annotations

from datetime import datetime, timezone

from granular.extraction.coverage import CoverageIndex
from granular.schema import AlignmentStatus, Authority, Concept, ProvenanceRecord


def make_concept(concept_id: str, course_id: str, ku_id: str | None, status: AlignmentStatus) -> Concept:
    return Concept(
        provenance=ProvenanceRecord(
            source_url="https://catalog.purdue.edu/c/1",
            retrieved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            adapter_name="test",
            adapter_version="1.0.0",
            source_revision=None,
        ),
        model_id="m",
        confidence=0.8,
        concept_id=concept_id,
        authority=Authority.DERIVED,
        label="label",
        source_course_id=course_id,
        knowledge_unit_id=ku_id,
        alignment_status=status,
    )


class TestCoverageIndex:
    def test_builds_from_aligned_concepts(self):
        idx = CoverageIndex()
        idx.build([
            make_concept("c1", "CS-100", "KU-1", AlignmentStatus.ALIGNED),
            make_concept("c2", "CS-200", "KU-1", AlignmentStatus.ALIGNED),
        ])
        assert set(idx.courses_for_ku("KU-1")) == {"CS-100", "CS-200"}
        assert idx.coverage_count("KU-1") == 2

    def test_ignores_unaligned(self):
        idx = CoverageIndex()
        idx.build([
            make_concept("c1", "CS-100", None, AlignmentStatus.UNALIGNED),
        ])
        assert idx.coverage_count("KU-1") == 0

    def test_thin_coverage(self):
        idx = CoverageIndex()
        idx.build([
            make_concept("c1", "CS-100", "KU-1", AlignmentStatus.ALIGNED),
        ])
        # KU-1 has 1 course; with min_courses=2 it is thin
        assert "KU-1" in idx.thin_coverage_units(min_courses=2)
        # with min_courses=1 it is not thin
        assert "KU-1" not in idx.thin_coverage_units(min_courses=1)
