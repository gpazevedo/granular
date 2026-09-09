"""Tests for the prerequisite recursive-descent parser."""

from __future__ import annotations

import pytest

from granular.ingestion.adapters.acalog.prereq_parser import parse_prerequisite
from granular.schema import AndList, OrList, PrerequisiteRule, SingleCourse


def test_single_course():
    rule = parse_prerequisite("r-1", "CS 18000")
    assert rule.machine_checkable
    assert isinstance(rule.structured, SingleCourse)
    assert rule.structured.course_id == "CS-18000"


def test_single_course_with_grade():
    rule = parse_prerequisite("r-1", "CS 18000 (C or better)")
    assert rule.machine_checkable
    assert isinstance(rule.structured, SingleCourse)
    assert rule.structured.min_grade == "C"


def test_and_list():
    rule = parse_prerequisite("r-1", "CS 18000 and CS 18200")
    assert rule.machine_checkable
    assert isinstance(rule.structured, AndList)
    assert len(rule.structured.children) == 2
    assert rule.structured.children[0].course_id == "CS-18000"
    assert rule.structured.children[1].course_id == "CS-18200"


def test_or_list():
    rule = parse_prerequisite("r-1", "CS 18000 or CS 18200")
    assert rule.machine_checkable
    assert isinstance(rule.structured, OrList)
    assert len(rule.structured.children) == 2


def test_nested():
    rule = parse_prerequisite("r-1", "(CS 18000 or CS 18200) and CS 25100")
    assert rule.machine_checkable
    assert isinstance(rule.structured, AndList)
    assert len(rule.structured.children) == 2
    assert isinstance(rule.structured.children[0], OrList)
    assert isinstance(rule.structured.children[1], SingleCourse)


def test_three_way_and():
    rule = parse_prerequisite("r-1", "CS 18000 and CS 18200 and CS 25100")
    assert rule.machine_checkable
    assert isinstance(rule.structured, AndList)
    assert len(rule.structured.children) == 3


def test_prose_condition_not_machine_checkable():
    rule = parse_prerequisite("r-1", "Permission of instructor required")
    assert not rule.machine_checkable
    assert rule.verbatim_text == "Permission of instructor required"


def test_junior_standing_not_machine_checkable():
    rule = parse_prerequisite("r-1", "Junior standing or above")
    assert not rule.machine_checkable


def test_empty_prereq_not_machine_checkable():
    rule = parse_prerequisite("r-1", "")
    assert not rule.machine_checkable


def test_verbatim_always_retained():
    text = "CS 18000 or permission of instructor"
    rule = parse_prerequisite("r-1", text)
    assert rule.verbatim_text == text


def test_three_course_or_list():
    rule = parse_prerequisite("r-1", "CS 18000 or CS 18200 or MA 26100")
    assert rule.machine_checkable
    assert isinstance(rule.structured, OrList)
    assert len(rule.structured.children) == 3
