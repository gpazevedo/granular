"""Tests for UIUC static catalog parser."""

from granular.ingestion.adapters.uiuc.parser import parse_uiuc_catalog


SAMPLE_HTML = """
<html><body>
<div class="courseblock">
<p class="courseblocktitle"><strong>CS 100  Computer Science Orientation  credit: 1 Hour. </strong></p>
<p class="courseblockdesc">Introduction to Computer Science as a field and career.</p>
</div>
<div class="courseblock">
<p class="courseblocktitle"><strong>CS 101  Intro Computing: Engrg &amp; Sci  credit: 3 Hours. </strong></p>
<p class="courseblockdesc">Fundamental principles of computing. Prerequisite: MATH 220.</p>
</div>
</body></html>
"""


class TestUiucParser:
    def test_parses_course_blocks(self):
        courses = parse_uiuc_catalog(SAMPLE_HTML, "https://example.com/")
        assert len(courses) == 2

    def test_extracts_fields(self):
        courses = parse_uiuc_catalog(SAMPLE_HTML, "https://example.com/")
        c = courses[0]
        assert c.prefix == "CS"
        assert c.number == "100"
        assert "Orientation" in c.title
        assert c.credits == 1.0
        assert "Introduction to Computer Science" in c.description

    def test_handles_ampersand(self):
        courses = parse_uiuc_catalog(SAMPLE_HTML, "https://example.com/")
        assert "Engrg" in courses[1].title or "Sci" in courses[1].title

    def test_credits_float(self):
        courses = parse_uiuc_catalog(SAMPLE_HTML, "https://example.com/")
        assert courses[1].credits == 3.0
