"""ProgrammeParser — best-effort parse of Acalog programme HTML pages."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_COURSE_REF_RE = re.compile(r"\b([A-Z]{2,5})\s+(\d{5}[A-Z]?)\b")
_CREDIT_RE = re.compile(r"(\d+)\s+(?:credit\s+hours?|hours?|credits?)", re.IGNORECASE)
_GPA_RE = re.compile(r"(\d+\.\d+)\s+GPA", re.IGNORECASE)


@dataclass
class RawRequirementRule:
    verbatim_text: str
    rule_type_hint: Optional[str]  # "hours", "courses", "gpa", or None
    course_refs: list[str] = field(default_factory=list)  # "CS-18000" format


@dataclass
class RawProgramme:
    name: str
    level_raw: str  # "Undergraduate" / "Graduate"
    source_url: str
    requirement_rules: list[RawRequirementRule] = field(default_factory=list)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    source_revision: Optional[str] = None


def _extract_course_refs(text: str) -> list[str]:
    return [f"{m.group(1)}-{m.group(2)}" for m in _COURSE_REF_RE.finditer(text)]


def _detect_rule_type(text: str) -> Optional[str]:
    if _CREDIT_RE.search(text):
        return "hours"
    if _GPA_RE.search(text):
        return "gpa"
    if _COURSE_REF_RE.search(text):
        return "courses"
    return None


def parse_programme_page(
    html: str,
    source_url: str,
    source_revision: Optional[str] = None,
) -> Optional[RawProgramme]:
    """Parse one Acalog programme page (best-effort).

    Returns None if the page contains no recognisable programme structure.
    """
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(separator="\n", strip=True)

    # --- Programme name ---
    name = ""
    h1 = soup.find("h1")
    if h1:
        name = h1.get_text(strip=True)
    if not name:
        # Try first bold/strong in content area
        strong = soup.find("strong") or soup.find("b")
        if strong:
            name = strong.get_text(strip=True)
    if not name:
        logger.debug("Could not find programme name at %s", source_url)
        return None

    # --- Level ---
    level_raw = "Graduate"
    name_lower = name.lower()
    if any(kw in name_lower for kw in ("bachelor", "b.s.", "bs ", "undergraduate")):
        level_raw = "Undergraduate"

    # --- Requirement blocks ---
    # Each <li>, <p>, or table row in the programme content is a candidate rule.
    rules: list[RawRequirementRule] = []
    content_div = (
        soup.find("div", id="programrequirementstextcontainer")
        or soup.find("div", class_="tab_content")
        or soup.find("div", id="requirementstextcontainer")
        or soup.body
    )

    if content_div:
        for tag in content_div.find_all(["li", "p", "tr"]):
            text = tag.get_text(separator=" ", strip=True)
            if len(text) < 5:
                continue
            rule_type = _detect_rule_type(text)
            course_refs = _extract_course_refs(text)
            rules.append(
                RawRequirementRule(
                    verbatim_text=text,
                    rule_type_hint=rule_type,
                    course_refs=course_refs,
                )
            )

    if not rules:
        # Fallback: split page text into lines and treat each non-empty line as a rule
        for line in page_text.splitlines():
            line = line.strip()
            if len(line) < 10:
                continue
            rules.append(
                RawRequirementRule(
                    verbatim_text=line,
                    rule_type_hint=_detect_rule_type(line),
                    course_refs=_extract_course_refs(line),
                )
            )

    return RawProgramme(
        name=name[:300],
        level_raw=level_raw,
        source_url=source_url,
        requirement_rules=rules,
        retrieved_at=datetime.now(tz=timezone.utc),
        source_revision=source_revision,
    )
