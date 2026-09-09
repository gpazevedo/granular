"""CourseParser — parse one Acalog course detail HTML page into RawCourse."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_CREDIT_FIXED_RE = re.compile(r"(\d+(?:\.\d+)?)\s+(?:Credit\s+Hours?|credit\s+hours?|credits?)", re.IGNORECASE)
_CREDIT_RANGE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s+to\s+(\d+(?:\.\d+)?)\s+(?:Credit\s+Hours?|credit\s+hours?|credits?)", re.IGNORECASE
)


@dataclass
class RawCourse:
    subject_code: str
    course_number: str
    title: str
    description: str
    credits_raw: str
    prereqs_raw: str
    cross_list_raw: list[str] = field(default_factory=list)
    level_raw: str = "Undergraduate"
    source_url: str = ""
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    source_revision: Optional[str] = None


def parse_course_page(html: str, source_url: str, source_revision: Optional[str] = None) -> Optional[RawCourse]:
    """Parse one Acalog course detail page.

    Returns None if the page does not contain recognisable course data.
    """
    soup = BeautifulSoup(html, "html.parser")

    # --- Title block: "CS 18000 - Problem Solving And Object-Oriented Programming" ---
    title_tag = (
        soup.find("h1")
        or soup.find("td", class_="block_content")
        or soup.find("div", id="courseblockdesc")
    )

    # Acalog wraps course info in a specific structure; try multiple selectors
    # Primary: look for the course title in <h1> or the first strong/b in the content block
    course_title_text = ""
    subject_code = ""
    course_number = ""

    # Try to find "SUBJ NNNNN - Title" pattern anywhere in the page
    title_pattern = re.compile(r"\b([A-Z]{2,5})\s+(\d{5}[A-Z]?)\s*[-–]\s*(.+)", re.DOTALL)
    page_text = soup.get_text(separator=" ", strip=True)
    m = title_pattern.search(page_text)
    if m:
        subject_code = m.group(1).strip()
        course_number = m.group(2).strip()
        course_title_text = re.sub(r"\s+", " ", m.group(3)).split(".")[0].strip()
    else:
        logger.debug("Could not extract course code from %s", source_url)
        return None

    # --- Description ---
    description = ""
    # Look for the description block — typically after the title/credits lines
    desc_tag = soup.find("div", class_="courseblockdesc") or soup.find("td", class_="courseblockdesc")
    if desc_tag:
        description = desc_tag.get_text(separator=" ", strip=True)
    else:
        # Fallback: grab paragraphs after the title
        paras = [p.get_text(separator=" ", strip=True) for p in soup.find_all("p") if len(p.get_text()) > 40]
        description = " ".join(paras[:3])

    # --- Credits ---
    credits_raw = ""
    # Handle "Credit Hours: 4.00" (with colon) and "4.00 Credit Hours" (without)
    credit_colon_re = re.compile(r"Credit\s+Hours?\s*:\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
    credit_m = credit_colon_re.search(page_text) or _CREDIT_RANGE_RE.search(page_text) or _CREDIT_FIXED_RE.search(page_text)
    if credit_m:
        credits_raw = credit_m.group(0).strip()
    elif re.search(r"variable", page_text, re.IGNORECASE):
        credits_raw = "Variable"

    # --- Prerequisites ---
    prereqs_raw = ""
    prereq_pattern = re.compile(
        r"(?:Prerequisite[s]?|Pre-requisite[s]?)\s*:?\s*(.*?)(?:\n|\.(?:\s|$)|$)",
        re.IGNORECASE | re.DOTALL,
    )
    prereq_m = prereq_pattern.search(page_text)
    if prereq_m:
        prereqs_raw = re.sub(r"\s+", " ", prereq_m.group(1)).strip()

    # --- Cross-listings ---
    cross_list_raw: list[str] = []
    cross_pattern = re.compile(r"(?:Same as|Also offered as|Cross-listed with)\s+([A-Z]{2,5}\s+\d{5}[A-Z]?)", re.IGNORECASE)
    for xm in cross_pattern.finditer(page_text):
        cross_list_raw.append(xm.group(1).strip())

    # --- Level (undergraduate vs. graduate) ---
    level_raw = "Graduate" if int(course_number[:1] or "0") >= 5 else "Undergraduate"

    return RawCourse(
        subject_code=subject_code,
        course_number=course_number,
        title=course_title_text[:200],  # cap title length
        description=description,
        credits_raw=credits_raw,
        prereqs_raw=prereqs_raw,
        cross_list_raw=cross_list_raw,
        level_raw=level_raw,
        source_url=source_url,
        retrieved_at=datetime.now(tz=timezone.utc),
        source_revision=source_revision,
    )
