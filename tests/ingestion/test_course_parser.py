"""Tests for the Acalog course HTML parser."""

from __future__ import annotations

import pytest

from granular.ingestion.adapters.acalog.course_parser import parse_course_page


SAMPLE_COURSE_HTML = """
<html><body>
<h1>CS 18000 - Problem Solving And Object-Oriented Programming</h1>
<div class="courseblockdesc">
Introduction to problem solving and object-oriented programming. Variables, expressions,
conditionals, loops, functions, recursion, objects, classes. Laboratory.
</div>
<p>Credit Hours: 4.00</p>
<p>Prerequisite: None</p>
</body></html>
"""

SAMPLE_WITH_PREREQ_HTML = """
<html><body>
<h1>CS 25100 - Data Structures And Algorithms</h1>
<div class="courseblockdesc">
Abstract data types, data structures, and algorithms for searching, sorting, and graphs.
</div>
<p>Credit Hours: 3.00</p>
<p>Prerequisite: CS 18000 and CS 18200</p>
</body></html>
"""

SAMPLE_WITH_CROSSLIST_HTML = """
<html><body>
<h1>CS 38100 - Introduction to the Analysis of Algorithms</h1>
<div class="courseblockdesc">
Algorithm analysis and design techniques. Same as ECE 38100.
</div>
<p>Credit Hours: 3.00</p>
<p>Prerequisite: CS 25100 or CS 25200</p>
</body></html>
"""


class TestCourseParser:
    def test_basic_parse(self):
        raw = parse_course_page(SAMPLE_COURSE_HTML, "https://catalog.purdue.edu/course/1")
        assert raw is not None
        assert raw.subject_code == "CS"
        assert raw.course_number == "18000"
        assert "Problem Solving" in raw.title

    def test_credits_extracted(self):
        raw = parse_course_page(SAMPLE_COURSE_HTML, "https://catalog.purdue.edu/course/1")
        assert raw is not None
        assert "4" in raw.credits_raw

    def test_description_extracted(self):
        raw = parse_course_page(SAMPLE_COURSE_HTML, "https://catalog.purdue.edu/course/1")
        assert raw is not None
        assert "problem solving" in raw.description.lower()

    def test_prereq_extracted(self):
        raw = parse_course_page(SAMPLE_WITH_PREREQ_HTML, "https://catalog.purdue.edu/course/2")
        assert raw is not None
        assert "CS 18000" in raw.prereqs_raw

    def test_cross_listing_extracted(self):
        raw = parse_course_page(SAMPLE_WITH_CROSSLIST_HTML, "https://catalog.purdue.edu/course/3")
        assert raw is not None
        assert any("ECE" in x for x in raw.cross_list_raw)

    def test_level_inferred_from_course_number(self):
        raw = parse_course_page(SAMPLE_COURSE_HTML, "https://catalog.purdue.edu/course/1")
        assert raw is not None
        assert raw.level_raw == "Undergraduate"

    def test_source_url_stored(self):
        url = "https://catalog.purdue.edu/preview_course_nopop.php?coid=999"
        raw = parse_course_page(SAMPLE_COURSE_HTML, url)
        assert raw is not None
        assert raw.source_url == url

    def test_empty_html_returns_none(self):
        raw = parse_course_page("<html><body></body></html>", "https://example.com")
        assert raw is None
