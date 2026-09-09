"""Department hard-filter regression test (Task 8, REQ-EH-07 / REQ-CE-07).

Verifies the alignment reranker never uses department as a hard filter.
A cross-listed course's top-ranked candidate must be identical whether or not
the department signal is applied.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from granular.extraction.config import ExtractionConfig
from granular.extraction.extractor import RawConcept
from granular.extraction.pipeline.rerank import rerank
from granular.extraction.pipeline.retrieve import CandidateKU
from granular.schema import (
    Authority,
    Course,
    DeclaredEdge,
    DeclaredEdgeType,
    KnowledgeTier,
    KnowledgeUnit,
    ProgrammeLevel,
    ProvenanceRecord,
)


def _provenance() -> ProvenanceRecord:
    return ProvenanceRecord(
        source_url="https://catalog.purdue.edu/c/1",
        retrieved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        adapter_name="test",
        adapter_version="1.0.0",
        source_revision=None,
    )


def make_cross_listed_course() -> Course:
    """A CS course cross-listed with ECE (e.g. CS 38100 / ECE 38100)."""
    return Course(
        provenance=_provenance(),
        course_id="CS-38100",
        authority=Authority.DERIVED,
        subject_code="CS",
        course_number="38100",
        title="Introduction to the Analysis of Algorithms",
        description="Algorithm design and analysis. Same as ECE 38100.",
        credits=3.0,
        level=ProgrammeLevel.UNDERGRADUATE,
        cross_listings=["ECE-38100"],
    )


@pytest.mark.regression
def test_no_department_hard_filter():
    """The reranker must not exclude a candidate based on department, and the
    top-ranked candidate must not change when the department prior is removed.
    """
    course = make_cross_listed_course()
    assert course.cross_listings, "test requires a cross-listed course"

    concept = RawConcept(
        label="asymptotic complexity analysis",
        source_course_id=course.course_id,
        model_id="test-model",
    )
    candidates = [
        CandidateKU(ku_id="CS2023-AL-KU-1", label="Basic Analysis", similarity_score=0.82),
        CandidateKU(ku_id="CS2023-AR-KU-1", label="Digital Logic", similarity_score=0.55),
    ]
    ku_lookup = {
        "CS2023-AL-KU-1": KnowledgeUnit(
            ku_id="CS2023-AL-KU-1", label="Basic Analysis",
            knowledge_area="AL", tier=KnowledgeTier.CORE,
        ),
        "CS2023-AR-KU-1": KnowledgeUnit(
            ku_id="CS2023-AR-KU-1", label="Digital Logic",
            knowledge_area="AR", tier=KnowledgeTier.ELECTIVE,
        ),
    }

    # With the default department prior (small, non-zero weight)
    cfg_with_dept = ExtractionConfig()
    ranked_with = rerank(concept, candidates, course, [], ku_lookup, cfg_with_dept)

    # With department prior weight zeroed out
    cfg_no_dept = ExtractionConfig(weight_department_prior=0.0)
    ranked_without = rerank(concept, candidates, course, [], ku_lookup, cfg_no_dept)

    # No candidate is ever dropped by department
    assert len(ranked_with) == len(candidates)
    assert len(ranked_without) == len(candidates)

    # The top-ranked candidate must be the same regardless of the department signal
    assert ranked_with[0].ku_id == ranked_without[0].ku_id
