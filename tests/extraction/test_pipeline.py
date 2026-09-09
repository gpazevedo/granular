"""Tests for the alignment pipeline stages (network-free)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from granular.extraction.config import ExtractionConfig
from granular.extraction.extractor import RawConcept
from granular.extraction.pipeline.reject import (
    ConceptGraphSnapshot,
    RejectionRecord,
    reject,
)
from granular.extraction.pipeline.rerank import (
    RankedCandidateKU,
    _normalise_course_level,
    _ku_depth_proxy,
    rerank,
)
from granular.extraction.pipeline.retrieve import CandidateKU
from granular.extraction.pipeline.verify import verify
from granular.schema import (
    Authority,
    Course,
    KnowledgeTier,
    KnowledgeUnit,
    ProgrammeLevel,
    ProvenanceRecord,
    AlignmentStatus,
)


def make_course(number="38100") -> Course:
    return Course(
        provenance=ProvenanceRecord(
            source_url="https://catalog.purdue.edu/c/1",
            retrieved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            adapter_name="test",
            adapter_version="1.0.0",
            source_revision=None,
        ),
        course_id=f"CS-{number}",
        authority=Authority.DERIVED,
        subject_code="CS",
        course_number=number,
        title="Test Course",
        description="A description.",
        credits=3.0,
        level=ProgrammeLevel.UNDERGRADUATE,
    )


def make_config() -> ExtractionConfig:
    return ExtractionConfig()


class TestCourseLevelNormalisation:
    def test_100_level(self):
        assert _normalise_course_level("18000") == pytest.approx(0.0)

    def test_500_level(self):
        assert _normalise_course_level("59000") == pytest.approx(0.8)

    def test_invalid_defaults_to_middle(self):
        assert _normalise_course_level("abc") == 0.5


class TestKUDepthProxy:
    def test_core_is_foundational(self):
        assert _ku_depth_proxy(KnowledgeTier.CORE) < _ku_depth_proxy(KnowledgeTier.ELECTIVE)


class TestRerank:
    def test_orders_by_score(self):
        concept = RawConcept(label="binary trees", source_course_id="CS-25100", model_id="m")
        candidates = [
            CandidateKU(ku_id="KU-1", label="Trees", similarity_score=0.5),
            CandidateKU(ku_id="KU-2", label="Sorting", similarity_score=0.9),
        ]
        ku_lookup = {
            "KU-1": KnowledgeUnit(ku_id="KU-1", label="Trees", knowledge_area="AL", tier=KnowledgeTier.CORE),
            "KU-2": KnowledgeUnit(ku_id="KU-2", label="Sorting", knowledge_area="AL", tier=KnowledgeTier.CORE),
        }
        ranked = rerank(concept, candidates, make_course(), [], ku_lookup, make_config())
        # Higher similarity should rank higher when other signals are equal
        assert ranked[0].ku_id == "KU-2"

    def test_cooccurrence_boosts_matching_area(self):
        concept = RawConcept(label="regression", source_course_id="CS-47300", model_id="m")
        candidates = [
            CandidateKU(ku_id="KU-IS", label="ML", similarity_score=0.6),
            CandidateKU(ku_id="KU-AL", label="Algo", similarity_score=0.6),
        ]
        ku_lookup = {
            "KU-IS": KnowledgeUnit(ku_id="KU-IS", label="ML", knowledge_area="IS", tier=KnowledgeTier.ELECTIVE),
            "KU-AL": KnowledgeUnit(ku_id="KU-AL", label="Algo", knowledge_area="AL", tier=KnowledgeTier.CORE),
        }
        # Co-concepts are all in IS area
        ranked = rerank(concept, candidates, make_course("47300"), ["IS", "IS"], ku_lookup, make_config())
        assert ranked[0].ku_id == "KU-IS"


class TestReject:
    def test_no_violations_all_survive(self):
        concept = RawConcept(label="x", source_course_id="CS-100", model_id="m")
        candidates = [
            RankedCandidateKU(ku_id="KU-1", label="A", similarity_score=0.5, rerank_score=0.6),
        ]
        snapshot = ConceptGraphSnapshot()
        result = reject(concept, candidates, 0.5, snapshot)
        assert len(result.surviving) == 1
        assert len(result.rejections) == 0

    def test_ordering_violation_rejected(self):
        concept = RawConcept(label="x", source_course_id="CS-100", model_id="m")
        candidates = [
            RankedCandidateKU(ku_id="KU-1", label="A", similarity_score=0.5, rerank_score=0.6),
        ]
        snapshot = ConceptGraphSnapshot()
        # KU-1 has only been aligned to high-level (0.8) courses
        snapshot.record_alignment("KU-1", 0.8)
        # Now try to align a low-level (0.0) course to it
        result = reject(concept, candidates, 0.0, snapshot)
        assert len(result.surviving) == 0
        assert result.rejections[0].reason == "ordering_violation"


class TestVerify:
    def test_no_candidates_unaligned(self):
        result = verify([], make_config())
        assert result.status == AlignmentStatus.UNALIGNED
        assert result.knowledge_unit_id is None

    def test_high_confidence_aligned(self):
        candidates = [
            RankedCandidateKU(ku_id="KU-1", label="A", similarity_score=0.9, rerank_score=0.9),
            RankedCandidateKU(ku_id="KU-2", label="B", similarity_score=0.1, rerank_score=0.1),
        ]
        result = verify(candidates, make_config())
        assert result.status == AlignmentStatus.ALIGNED
        assert result.knowledge_unit_id == "KU-1"
        assert result.confidence > 0.5

    def test_low_confidence_unaligned(self):
        # Two near-equal candidates → low confidence
        candidates = [
            RankedCandidateKU(ku_id="KU-1", label="A", similarity_score=0.5, rerank_score=0.11),
            RankedCandidateKU(ku_id="KU-2", label="B", similarity_score=0.5, rerank_score=0.10),
        ]
        cfg = make_config()
        cfg.min_confidence = 0.6  # force low-confidence classification
        result = verify(candidates, cfg)
        assert result.status == AlignmentStatus.LOW_CONFIDENCE_UNALIGNED
