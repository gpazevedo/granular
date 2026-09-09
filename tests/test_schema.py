"""Tests for granular.schema — canonical schema package."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from granular.schema import (
    AlignmentStatus,
    AndList,
    Authority,
    Concept,
    Course,
    CreditRange,
    DeclaredEdge,
    DeclaredEdgeType,
    InferredEdge,
    InferredEdgeType,
    KnowledgeTier,
    KnowledgeUnit,
    OrList,
    PrerequisiteRule,
    Programme,
    ProgrammeLevel,
    ProvenanceRecord,
    RequirementRule,
    RuleType,
    SchemaValidationError,
    SingleCourse,
    to_dict,
    to_json,
    validate_all,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_provenance(**kwargs) -> ProvenanceRecord:
    defaults = dict(
        source_url="https://catalog.purdue.edu/preview_course.php?coid=123",
        retrieved_at=datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        adapter_name="purdue_acalog",
        adapter_version="1.0.0",
        source_revision="2026-2027",
    )
    defaults.update(kwargs)
    return ProvenanceRecord(**defaults)


def make_course(**kwargs) -> Course:
    defaults = dict(
        provenance=make_provenance(),
        course_id="CS-38100",
        authority=Authority.DERIVED,
        subject_code="CS",
        course_number="38100",
        title="Information Systems",
        description="Introduction to databases and information systems.",
        credits=3.0,
        level=ProgrammeLevel.UNDERGRADUATE,
    )
    defaults.update(kwargs)
    return Course(**defaults)


def make_inferred_edge(**kwargs) -> InferredEdge:
    defaults = dict(
        provenance=make_provenance(),
        model_id="granular-inference/1.0.0",
        confidence=0.8,
        edge_id="ie-001",
        from_id="concept-A",
        to_id="concept-B",
        relationship_type=InferredEdgeType.CONCEPT_DEPENDENCY,
    )
    defaults.update(kwargs)
    return InferredEdge(**defaults)


# ---------------------------------------------------------------------------
# ProvenanceRecord
# ---------------------------------------------------------------------------

class TestProvenanceRecord:
    def test_valid(self):
        p = make_provenance()
        assert p.adapter_name == "purdue_acalog"

    def test_rejects_naive_datetime(self):
        with pytest.raises(SchemaValidationError) as exc:
            make_provenance(retrieved_at=datetime(2026, 9, 1, 12, 0, 0))
        assert "timezone-aware" in str(exc.value)

    def test_rejects_empty_adapter_name(self):
        with pytest.raises(SchemaValidationError):
            make_provenance(adapter_name="")

    def test_rejects_bad_url(self):
        with pytest.raises(SchemaValidationError):
            make_provenance(source_url="ftp://example.com")

    def test_source_revision_none_allowed(self):
        p = make_provenance(source_revision=None)
        assert p.source_revision is None

    def test_now_constructor(self):
        p = ProvenanceRecord.now(
            source_url="https://example.com",
            adapter_name="test",
            adapter_version="1.0.0",
        )
        assert p.retrieved_at.tzinfo is not None


# ---------------------------------------------------------------------------
# DeclaredEdge
# ---------------------------------------------------------------------------

class TestDeclaredEdge:
    def test_valid(self):
        e = DeclaredEdge(
            provenance=make_provenance(),
            edge_id="de-001",
            from_id="CS-18000",
            to_id="CS-25100",
            relationship_type=DeclaredEdgeType.PREREQUISITE,
        )
        assert e.relationship_type == DeclaredEdgeType.PREREQUISITE

    def test_rejects_empty_edge_id(self):
        with pytest.raises(SchemaValidationError):
            DeclaredEdge(
                provenance=make_provenance(),
                edge_id="",
                from_id="CS-18000",
                to_id="CS-25100",
                relationship_type=DeclaredEdgeType.PREREQUISITE,
            )

    def test_has_no_confidence_field(self):
        e = DeclaredEdge(
            provenance=make_provenance(),
            edge_id="de-001",
            from_id="CS-18000",
            to_id="CS-25100",
            relationship_type=DeclaredEdgeType.PREREQUISITE,
        )
        assert not hasattr(e, "confidence")
        assert not hasattr(e, "model_id")


# ---------------------------------------------------------------------------
# InferredEdge
# ---------------------------------------------------------------------------

class TestInferredEdge:
    def test_valid(self):
        e = make_inferred_edge()
        assert e.confidence == 0.8

    def test_rejects_empty_model_id(self):
        with pytest.raises(SchemaValidationError):
            make_inferred_edge(model_id="")

    def test_rejects_confidence_out_of_range(self):
        with pytest.raises(SchemaValidationError):
            make_inferred_edge(confidence=1.5)
        with pytest.raises(SchemaValidationError):
            make_inferred_edge(confidence=-0.1)

    def test_boundary_confidences(self):
        assert make_inferred_edge(confidence=0.0).confidence == 0.0
        assert make_inferred_edge(confidence=1.0).confidence == 1.0


# ---------------------------------------------------------------------------
# PrerequisiteRule
# ---------------------------------------------------------------------------

class TestPrerequisiteRule:
    def test_machine_checkable_with_structured(self):
        rule = PrerequisiteRule(
            rule_id="r-001",
            verbatim_text="CS 18000",
            machine_checkable=True,
            structured=SingleCourse(course_id="CS-18000"),
        )
        assert rule.machine_checkable

    def test_machine_checkable_requires_structured(self):
        with pytest.raises(SchemaValidationError):
            PrerequisiteRule(
                rule_id="r-001",
                verbatim_text="CS 18000",
                machine_checkable=True,
                structured=None,
            )

    def test_not_machine_checkable_requires_verbatim(self):
        with pytest.raises(SchemaValidationError):
            PrerequisiteRule(
                rule_id="r-001",
                verbatim_text="",
                machine_checkable=False,
            )

    def test_not_machine_checkable_structured_must_be_none(self):
        with pytest.raises(SchemaValidationError):
            PrerequisiteRule(
                rule_id="r-001",
                verbatim_text="Some text",
                machine_checkable=False,
                structured=SingleCourse(course_id="CS-18000"),
            )


# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------

class TestCourse:
    def test_valid(self):
        c = make_course()
        assert c.subject_code == "CS"

    def test_rejects_empty_subject_code(self):
        with pytest.raises(SchemaValidationError):
            make_course(subject_code="")

    def test_rejects_empty_course_number(self):
        with pytest.raises(SchemaValidationError):
            make_course(course_number="")

    def test_credit_range(self):
        c = make_course(credits=CreditRange(1.0, 3.0))
        assert isinstance(c.credits, CreditRange)

    def test_credit_range_invalid(self):
        with pytest.raises(SchemaValidationError):
            CreditRange(3.0, 1.0)


# ---------------------------------------------------------------------------
# Programme
# ---------------------------------------------------------------------------

class TestProgramme:
    def test_valid(self):
        rule = RequirementRule(
            rule_id="r-001",
            rule_type=RuleType.MINIMUM_CREDITS,
            verbatim_text="Minimum 120 credit hours",
            machine_checkable=False,
        )
        p = Programme(
            provenance=make_provenance(),
            programme_id="prog-bscs",
            authority=Authority.DERIVED,
            name="BS Computer Science",
            level=ProgrammeLevel.UNDERGRADUATE,
            department="Computer Science",
            catalogue_url="https://catalog.purdue.edu/",
            requirement_rules=[rule],
        )
        assert p.name == "BS Computer Science"

    def test_rejects_empty_requirement_rules(self):
        with pytest.raises(SchemaValidationError):
            Programme(
                provenance=make_provenance(),
                programme_id="prog-bscs",
                authority=Authority.DERIVED,
                name="BS Computer Science",
                level=ProgrammeLevel.UNDERGRADUATE,
                department="Computer Science",
                catalogue_url="https://catalog.purdue.edu/",
                requirement_rules=[],
            )


# ---------------------------------------------------------------------------
# Concept
# ---------------------------------------------------------------------------

class TestConcept:
    def test_valid(self):
        c = Concept(
            provenance=make_provenance(),
            model_id="gpt-4o-mini",
            confidence=0.75,
            concept_id="concept-001",
            authority=Authority.DERIVED,
            label="Maximum likelihood estimation",
            source_course_id="CS-47300",
            knowledge_unit_id="CS2023-MSF-KU-3",
            alignment_status=AlignmentStatus.ALIGNED,
        )
        assert c.label == "Maximum likelihood estimation"

    def test_rejects_non_derived_authority(self):
        with pytest.raises(SchemaValidationError):
            Concept(
                provenance=make_provenance(),
                model_id="gpt-4o-mini",
                confidence=0.75,
                concept_id="concept-001",
                authority=Authority.REGISTRAR,
                label="MLE",
                source_course_id="CS-47300",
                alignment_status=AlignmentStatus.ALIGNED,
            )

    def test_rejects_empty_model_id(self):
        with pytest.raises(SchemaValidationError):
            Concept(
                provenance=make_provenance(),
                model_id="",
                confidence=0.75,
                concept_id="concept-001",
                authority=Authority.DERIVED,
                label="MLE",
                source_course_id="CS-47300",
                alignment_status=AlignmentStatus.ALIGNED,
            )


# ---------------------------------------------------------------------------
# KnowledgeUnit
# ---------------------------------------------------------------------------

class TestKnowledgeUnit:
    def test_valid(self):
        ku = KnowledgeUnit(
            ku_id="CS2023-AL-KU-1",
            label="Basic Analysis",
            knowledge_area="AL",
            tier=KnowledgeTier.CORE,
        )
        assert ku.source == "CS2023"

    def test_rejects_wrong_source(self):
        with pytest.raises(SchemaValidationError):
            KnowledgeUnit(
                ku_id="KU-1",
                label="Basic Analysis",
                knowledge_area="AL",
                tier=KnowledgeTier.CORE,
                source="OTHER",
            )


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

class TestSerialisation:
    def test_course_round_trip(self):
        c = make_course()
        d = to_dict(c)
        assert d["subject_code"] == "CS"
        assert d["provenance"]["adapter_name"] == "purdue_acalog"

    def test_to_json_produces_valid_json(self):
        c = make_course()
        s = to_json(c)
        parsed = json.loads(s)
        assert parsed["course_id"] == "CS-38100"

    def test_inferred_edge_round_trip(self):
        e = make_inferred_edge()
        d = to_dict(e)
        assert d["confidence"] == 0.8
        assert d["model_id"] == "granular-inference/1.0.0"


# ---------------------------------------------------------------------------
# validate_all
# ---------------------------------------------------------------------------

class TestValidateAll:
    def test_all_pass(self):
        records = [make_course(), make_course(course_id="CS-25100", course_number="25100")]
        report = validate_all(records)
        assert report.all_passed
        assert len(report.passed) == 2
        assert len(report.failed) == 0

    def test_collects_all_failures(self):
        """validate_all must not stop at the first failure."""
        good = make_course()
        # Mutate post-construction to simulate bad state for re-validation
        bad1 = make_course()
        bad1.subject_code = ""   # will fail re-validation
        bad2 = make_course()
        bad2.course_number = ""  # will fail re-validation
        report = validate_all([good, bad1, bad2])
        assert len(report.failed) == 2
        assert len(report.passed) == 1
