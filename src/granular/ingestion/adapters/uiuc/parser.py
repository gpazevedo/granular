"""Parser for UIUC static course catalog.

URL: https://catalog.illinois.edu/courses-of-instruction/cs/

Each course is a <div class="courseblock"> with:
  - <p class="courseblocktitle">: "CS 100  Computer Science Orientation  credit: 1 Hour."
  - <p class="courseblockdesc">: description text (may include prerequisites)

Simple static HTML — no Acalog, no JavaScript, no bot mitigation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_COURSE_TITLE_RE = re.compile(
    r"^(?P<prefix>[A-Z]+)\s*(?P<number>\d+)\s+(?P<title>.+?)\s+credit:\s*(?P<credits>[\d.]+)\s+Hour",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class UiucCourseBlock:
    prefix: str  # "CS"
    number: str  # "100"
    title: str
    credits: float
    description: str
    source_url: str


def parse_uiuc_catalog(html: str, source_url: str) -> list[UiucCourseBlock]:
    """Parse all course blocks from UIUC catalog HTML."""
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.find_all("div", class_="courseblock")
    courses = []
    for block in blocks:
        title_p = block.find("p", class_="courseblocktitle")
        desc_p = block.find("p", class_="courseblockdesc")
        if not title_p:
            continue
        title_text = title_p.get_text(" ", strip=True)
        m = _COURSE_TITLE_RE.match(title_text)
        if not m:
            logger.debug("Skipping non-matching title: %s", title_text[:60])
            continue
        prefix = m.group("prefix").upper()
        number = m.group("number")
        title = m.group("title").strip()
        try:
            credits = float(m.group("credits"))
        except ValueError:
            credits = 0.0
        description = desc_p.get_text(" ", strip=True) if desc_p else ""
        courses.append(
            UiucCourseBlock(
                prefix=prefix,
                number=number,
                title=title,
                credits=credits,
                description=description,
                source_url=source_url,
            )
        )
    return courses
