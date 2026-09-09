"""Parser for Purdue CS canonical syllabus pages.

URL pattern:
  https://www.cs.purdue.edu/academic-programs/courses/canonical/csNNN.html
where NNN is the first three digits of the 5-digit course number
(CS 25200 -> cs252).

Each page carries:
  - an <h1> with "CS NNN: Title"
  - a "Prerequisite:" section listing declared course references
  - a "Detailed Syllabus:" section — a topic outline used as the description

Returns a CanonicalCourse intermediate. Missing sections are tolerated
(research artefact: extract what exists, flag the rest).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_COURSE_REF_RE = re.compile(r"\bCS\s*(\d{3,5})\b")


@dataclass
class CanonicalCourse:
    course_number_3: str          # e.g. "252"
    title: str
    description: str              # the detailed-syllabus outline text
    prerequisite_refs: list[str]  # normalised course_ids, e.g. ["CS-25000"]
    source_url: str
    has_description: bool = field(init=False)

    def __post_init__(self) -> None:
        self.has_description = len(self.description.strip()) >= 20


def course_number_to_slug(course_number: str) -> str:
    """Map a 5-digit OData course number to a canonical page slug.

    CS 25200 -> 'cs252'. Uses the first three digits.
    """
    digits = re.sub(r"\D", "", course_number)
    return "cs" + digits[:3]


def _normalise_ref(raw_digits: str) -> str:
    """Normalise a CS course reference to a 5-digit course_id.

    Canonical pages write 5-digit numbers ("CS 18000"); some write 3-digit
    ("CS 180"). Pad 3-digit to 5-digit (180 -> 18000).
    """
    if len(raw_digits) == 3:
        raw_digits = raw_digits + "00"
    return f"CS-{raw_digits}"


def parse_canonical_page(html: str, source_url: str) -> Optional[CanonicalCourse]:
    """Parse a canonical syllabus page. Returns None if it is not a course page."""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup.find("article") or soup

    h1 = main.find("h1")
    if not h1:
        return None
    heading = h1.get_text(" ", strip=True)
    # "CS 252: Systems Programming"
    m = re.match(r"CS\s*(\d{3,5})\s*:?\s*(.*)", heading)
    if not m:
        return None
    number_3 = m.group(1)[:3]
    title = m.group(2).strip() or heading

    text = main.get_text("\n", strip=True)

    # --- Prerequisites ---
    prereq_refs: list[str] = []
    prereq_idx = text.lower().find("prerequisite")
    syllabus_idx = text.lower().find("detailed syllabus")
    if prereq_idx >= 0:
        end = syllabus_idx if syllabus_idx > prereq_idx else prereq_idx + 300
        prereq_block = text[prereq_idx:end]
        for pm in _COURSE_REF_RE.finditer(prereq_block):
            prereq_refs.append(_normalise_ref(pm.group(1)))

    # --- Description (detailed syllabus outline) ---
    description = ""
    if syllabus_idx >= 0:
        # Take everything after "Detailed Syllabus:" up to a reasonable cap,
        # stripping trailing site boilerplate/footer noise.
        raw = text[syllabus_idx + len("Detailed Syllabus:") :].strip()
        # Cut at common footer markers if present
        for marker in ("\nHome\n", "\nContact", "\n© ", "\nPurdue University,"):
            cut = raw.find(marker)
            if cut > 0:
                raw = raw[:cut]
        description = re.sub(r"\n{2,}", " ", raw).strip()[:4000]

    return CanonicalCourse(
        course_number_3=number_3,
        title=title[:200],
        description=description,
        prerequisite_refs=list(dict.fromkeys(prereq_refs)),  # dedupe, keep order
        source_url=source_url,
    )
