"""Tests for the CS canonical syllabus page parser."""

from __future__ import annotations

from granular.ingestion.adapters.cs_canonical.parser import (
    course_number_to_slug,
    parse_canonical_page,
)


SAMPLE = """
<html><body><main>
<h1>CS 252: Systems Programming</h1>
<p>Prerequisite:</p>
<p>CS 25000 (Computer Architecture)</p>
<p>CS 25100 (Data Structures and Algorithms)</p>
<p>Detailed Syllabus:</p>
<p>Program Generation, Representation, and Transformation. Compilers, linkers,
loaders and binding times. File systems, inodes, hard and symbolic links.</p>
</main></body></html>
"""

SAMPLE_3DIGIT_PREREQ = """
<html><body><main>
<h1>CS 182: Foundations of Computer Science</h1>
<p>Prerequisite: CS 180 (Problem Solving)</p>
<p>Detailed Syllabus: Logic and proofs, sets, functions, relations, induction.</p>
</main></body></html>
"""

NO_SYLLABUS = """
<html><body><main>
<h1>CS 180: Problem Solving</h1>
<p>Some intro text with no syllabus section.</p>
</main></body></html>
"""


class TestSlug:
    def test_five_digit(self):
        assert course_number_to_slug("25200") == "cs252"

    def test_maps_first_three_digits(self):
        assert course_number_to_slug("18000") == "cs180"


class TestParseCanonical:
    def test_extracts_title(self):
        c = parse_canonical_page(SAMPLE, "https://x/cs252.html")
        assert c is not None
        assert "Systems Programming" in c.title
        assert c.course_number_3 == "252"

    def test_extracts_prerequisites(self):
        c = parse_canonical_page(SAMPLE, "https://x/cs252.html")
        assert "CS-25000" in c.prerequisite_refs
        assert "CS-25100" in c.prerequisite_refs

    def test_extracts_description(self):
        c = parse_canonical_page(SAMPLE, "https://x/cs252.html")
        assert c.has_description
        assert "compilers" in c.description.lower()

    def test_three_digit_prereq_padded(self):
        c = parse_canonical_page(SAMPLE_3DIGIT_PREREQ, "https://x/cs182.html")
        # "CS 180" should normalise to CS-18000
        assert "CS-18000" in c.prerequisite_refs

    def test_no_syllabus_no_description(self):
        c = parse_canonical_page(NO_SYLLABUS, "https://x/cs180.html")
        assert c is not None
        assert not c.has_description

    def test_non_course_page_returns_none(self):
        c = parse_canonical_page("<html><body>No heading here</body></html>", "https://x/y.html")
        assert c is None
