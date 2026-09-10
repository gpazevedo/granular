"""Tests for LLM alignment verification (Stage 4b)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from granular.extraction.aligner import Aligner
from granular.extraction.config import ExtractionConfig
from granular.extraction.extractor import RawConcept
from granular.extraction.pipeline.verify import llm_confirms_alignment
from granular.schema import (
    AlignmentStatus,
    Authority,
    Course,
    CreditRange,
    KnowledgeTier,
    KnowledgeUnit,
    ProgrammeLevel,
    ProvenanceRecord,
)


class FakeProvider:
    """Chat provider returning a canned belongs verdict; records call count."""

    def __init__(self, belongs: bool | str) -> None:
        self._belongs = belongs
        self.calls = 0

    def chat_completion(self, system, user_message, model, temperature=0.0, response_format=None):
        self.calls += 1
        if isinstance(self._belongs, str):
            return self._belongs  # raw (possibly malformed) payload
        return json.dumps({"belongs": self._belongs})

    def embedding(self, text, model):  # pragma: no cover - not used here
        raise NotImplementedError


class RaisingProvider:
    def chat_completion(self, *a, **k):
        raise RuntimeError("LLM down")

    def embedding(self, *a, **k):  # pragma: no cover
        raise NotImplementedError


# --- llm_confirms_alignment --------------------------------------------------

class TestLlmConfirmsAlignment:
    def test_accepts_true(self):
        assert llm_confirms_alignment("software design", "Software Design and Architecture",
                                      FakeProvider(True), "m") is True

    def test_rejects_false(self):
        assert llm_confirms_alignment("construction of solar cars", "Software Construction and Verification",
                                      FakeProvider(False), "m") is False

    def test_fails_open_on_error(self):
        # On provider error, accept (fail-open) rather than drop pipeline output.
        assert llm_confirms_alignment("x", "y", RaisingProvider(), "m") is True

    def test_fails_open_on_malformed_json(self):
        assert llm_confirms_alignment("x", "y", FakeProvider("not json"), "m") is True

    def test_missing_key_accepts(self):
        assert llm_confirms_alignment("x", "y", FakeProvider('{"other": 1}' ), "m") is True


# --- Aligner Stage 4b integration --------------------------------------------

def _course() -> Course:
    return Course(
        provenance=ProvenanceRecord(
            source_url="https://x/1",
            retrieved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            adapter_name="test",
            adapter_version="1.0.0",
            source_revision=None,
        ),
        course_id="ECE-217",
        authority=Authority.DERIVED,
        subject_code="ECE",
        course_number="217",
        title="Solar Cars",
        description="Design and construction of solar-powered electric vehicles.",
        credits=CreditRange(3, 3),
        level=ProgrammeLevel.UNDERGRADUATE,
    )


class FakeEmbedder:
    """Returns one candidate KU so retrieve/verify yield a single ALIGNED winner."""

    def embed_text(self, text):
        return [0.1]

    def top_k_similar(self, vector, entity_type, k):
        return [("KU-SE", "Software Construction and Verification", 0.95)]


def _aligner(verify_model: str, provider) -> Aligner:
    cfg = ExtractionConfig(alignment_verify_model_id=verify_model)
    ku_lookup = {
        "KU-SE": KnowledgeUnit(
            ku_id="KU-SE",
            label="Software Construction and Verification",
            knowledge_area="SE",
            tier=KnowledgeTier.CORE,
        )
    }
    a = Aligner(FakeEmbedder(), ku_lookup, cfg)
    a._verify_provider = provider  # inject fake
    return a


def _raw() -> RawConcept:
    return RawConcept(
        label="construction of solar-powered electric vehicles",
        source_course_id="ECE-217",
        model_id="m",
    )


class TestAlignerVerification:
    def test_rejected_alignment_becomes_low_confidence(self):
        aligner = _aligner("openai/gpt-4o-mini", FakeProvider(False))
        concept = aligner.align(_raw(), _course(), [])
        assert concept.alignment_status == AlignmentStatus.LOW_CONFIDENCE_UNALIGNED
        assert concept.knowledge_unit_id is None

    def test_confirmed_alignment_stays_aligned(self):
        aligner = _aligner("openai/gpt-4o-mini", FakeProvider(True))
        concept = aligner.align(_raw(), _course(), [])
        assert concept.alignment_status == AlignmentStatus.ALIGNED
        assert concept.knowledge_unit_id == "KU-SE"

    def test_verification_disabled_skips_llm(self):
        provider = FakeProvider(False)
        aligner = _aligner("", provider)  # empty model disables verification
        concept = aligner.align(_raw(), _course(), [])
        # Would-be-rejected concept stays aligned because the LLM is never called.
        assert concept.alignment_status == AlignmentStatus.ALIGNED
        assert provider.calls == 0
