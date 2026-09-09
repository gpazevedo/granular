"""Tests for the course/programme normaliser."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from granular.ingestion.adapters.acalog.course_parser import RawCourse
from granular.ingestion.adapters.acalog.programme_parser import RawProgramme, RawRequirementRule
from granular.ingestion.config import IngestConfig
from granular.ingestion.normaliser import NormaliserError, normalise_course, normalise_programme
from granular.schema import (
    AndList,
    Course,
    CreditRange,
    DeclaredEdge,
    DeclaredEdgeType,
    OrList,
    ProgrammeLevel,
    SingleCourse,
)


def make_config() -> IngestConfig:
    return IngestConfig()


def make_raw_course(**kwargs) -> RawCourse:
    defaults = dict(
        subject_code="CS",
        course_number="38100",
        title="Information Systems",
        description="Intro to databases.",
        credits_raw="3.00 Credit Hours",
        prereqs_raw="CS 18000",
        cross_list_raw=[],
        level_raw="Undergraduate",
        source_url="https://catalog.purdue.edu/preview_course_nopop.php?coid=123",
        retrieved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        source_revision="2026-2027",
    )
    defaults.update(kwargs)
    return RawCourse(**defaults)


class TestNormaliseCourse:
    def test_basic_course(self):
        raw = make_raw_course()
        course, edges = normalise_course(raw, make_config())
        assert course.course_id == "CS-38100"
        assert course.subject_code == "CS"
        assert course.credits == 3.0
        assert course.level == ProgrammeLevel.UNDERGRADUATE

    def test_credit_range(self):
        raw = make_raw_course(credits_raw="1.00 to 3.00 Credit Hours")
        course, _ = normalise_course(raw, make_config())
        assert isinstance(course.credits, CreditRange)
        assert course.credits.min_credits == 1.0
        assert course.credits.max_credits == 3.0

    def test_variable_credits(self):
        raw = make_raw_course(credits_raw="Variable")
        course, _ = normalise_course(raw, make_config())
        assert isinstance(course.credits, CreditRange)
        assert course.credits.min_credits == 0.0

    def test_prerequisite_produces_declared_edge(self):
        raw = make_raw_course(prereqs_raw="CS 18000")
        _, edges = normalise_course(raw, make_config())
        prereq_edges = [e for e in edges if e.relationship_type == DeclaredEdgeType.PREREQUISITE]
        assert len(prereq_edges) == 1
        assert prereq_edges[0].to_id == "CS-18000"
        assert prereq_edges[0].from_id == "CS-38100"

    def test_prose_prereq_no_edge(self):
        raw = make_raw_course(prereqs_raw="Permission of instructor")
        _, edges = normalise_course(raw, make_config())
        prereq_edges = [e for e in edges if e.relationship_type == DeclaredEdgeType.PREREQUISITE]
        assert len(prereq_edges) == 0

    def test_cross_listing_produces_edge(self):
        raw = make_raw_course(cross_list_raw=["ECE 40400"])
        course, edges = normalise_course(raw, make_config())
        cross_edges = [e for e in edges if e.relationship_type == DeclaredEdgeType.CROSS_LISTING]
        assert len(cross_edges) == 1
        assert "ECE-40400" in course.cross_listings

    def test_graduate_level(self):
        raw = make_raw_course(course_number="59000", level_raw="Graduate")
        course, _ = normalise_course(raw, make_config())
        assert course.level == ProgrammeLevel.GRADUATE

    def test_provenance_fields(self):
        raw = make_raw_course()
        course, _ = normalise_course(raw, make_config())
        assert course.provenance.adapter_name == "purdue_acalog"
        assert course.provenance.source_revision == "2026-2027"

    def test_and_prereq_produces_multiple_edges(self):
        raw = make_raw_course(prereqs_raw="CS 18000 and CS 18200")
        _, edges = normalise_course(raw, make_config())
        prereq_edges = [e for e in edges if e.relationship_type == DeclaredEdgeType.PREREQUISITE]
        assert len(prereq_edges) == 2


class TestNormaliseProgramme:
    def test_basic_programme(self):
        raw = RawProgramme(
            name="BS Computer Science",
            level_raw="Undergraduate",
            source_url="https://catalog.purdue.edu/programme",
            requirement_rules=[
                RawRequirementRule(
                    verbatim_text="Minimum 120 credit hours",
                    rule_type_hint="hours",
                )
            ],
            retrieved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        prog = normalise_programme(raw, make_config())
        assert prog.name == "BS Computer Science"
        assert prog.level == ProgrammeLevel.UNDERGRADUATE
        assert len(prog.requirement_rules) == 1

    def test_empty_rules_gets_placeholder(self):
        raw = RawProgramme(
            name="MS Computer Science",
            level_raw="Graduate",
            source_url="https://catalog.purdue.edu/ms",
            requirement_rules=[],
            retrieved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        prog = normalise_programme(raw, make_config())
        assert len(prog.requirement_rules) == 1
        assert not prog.requirement_rules[0].machine_checkable

    def test_all_rules_not_machine_checkable(self):
        raw = RawProgramme(
            name="PhD Computer Science",
            level_raw="Graduate",
            source_url="https://catalog.purdue.edu/phd",
            requirement_rules=[
                RawRequirementRule("Complete 90 credit hours", "hours"),
                RawRequirementRule("CS 59800 or equivalent", "courses"),
            ],
            retrieved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        prog = normalise_programme(raw, make_config())
        assert all(not r.machine_checkable for r in prog.requirement_rules)
