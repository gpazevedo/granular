"""CS2023PdfParser — extract KnowledgeUnit records from the CS2023 PDF.

This is a one-time bootstrap step. The output is written to
data/cs2023_vocabulary.json and committed to the repository.

CS2023 document structure:
  - Knowledge areas appear as sections with 2–3 letter codes (e.g. AL, AR, CN)
  - Knowledge units are subsections within each area
  - Tier (Core/Elective) and contact hours are stated per unit

We parse the PDF text-layer directly using pdfplumber.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# CS2023 knowledge area codes and names (17 areas, used as a reference anchor)
_KNOWN_AREAS: dict[str, str] = {
    "AL": "Algorithms and Complexity",
    "AR": "Architecture and Organization",
    "CN": "Computational Science",
    "DS": "Discrete Structures",
    "GIT": "Graphics and Interactive Techniques",
    "HCI": "Human-Computer Interaction",
    "IAS": "Information Assurance and Security",
    "IM": "Information Management",
    "IS": "Intelligent Systems",
    "MSF": "Mathematical and Statistical Foundations",
    "NC": "Networking and Communication",
    "OS": "Operating Systems",
    "PBD": "Platform-Based Development",
    "PD": "Parallel and Distributed Computing",
    "PL": "Programming Languages",
    "SDF": "Software Development Fundamentals",
    "SE": "Software Engineering",
    "SF": "Systems Fundamentals",
    "SP": "Social Issues and Professional Practice",
}

_KA_HEADER_RE = re.compile(
    r"^(?P<code>[A-Z]{2,4})\s*[-–]\s*(?P<name>.+)$", re.MULTILINE
)
_KU_RE = re.compile(
    r"(?P<label>[A-Za-z][\w\s,\-/()]+?)\s+"
    r"(?P<tier>Core|Elective)\s+"
    r"(?P<hours>\d+(?:\.\d+)?)\s*hours?",
    re.IGNORECASE,
)
_TIER_RE = re.compile(r"\b(Core|Elective)\b", re.IGNORECASE)
_HOURS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*hours?", re.IGNORECASE)


@dataclass
class ParsedKU:
    ku_id: str
    label: str
    knowledge_area_code: str
    tier: str  # "core" or "elective"
    contact_hours: Optional[float]


def parse_cs2023_pdf(pdf_path: str) -> list[ParsedKU]:
    """Extract knowledge units from the CS2023 PDF.

    Attempts structured extraction first; falls back to heuristic extraction.
    Logs page ranges that could not be parsed but continues.

    Returns a list of ParsedKU records.
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError(
            "pdfplumber is required for PDF bootstrap. "
            "Install it with: pip install pdfplumber"
        )

    results: list[ParsedKU] = []
    current_area_code: Optional[str] = None
    ku_counter: dict[str, int] = {}

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                try:
                    text = page.extract_text() or ""
                    results.extend(
                        _parse_page(text, page_num, current_area_code, ku_counter)
                    )
                    # Update current area if a new one was found on this page
                    last_area = _find_last_area(text)
                    if last_area:
                        current_area_code = last_area
                except Exception as exc:
                    logger.warning(
                        "Could not parse page %d: %s", page_num, exc
                    )
    except Exception as exc:
        logger.error("Failed to open PDF %s: %s", pdf_path, exc)
        raise

    logger.info("Bootstrap: extracted %d knowledge units from %s", len(results), pdf_path)
    return results


def _find_last_area(text: str) -> Optional[str]:
    """Find the last knowledge area code mentioned on a page."""
    matches = _KA_HEADER_RE.findall(text)
    for code, _ in reversed(matches):
        if code in _KNOWN_AREAS:
            return code
    return None


def _parse_page(
    text: str,
    page_num: int,
    current_area: Optional[str],
    ku_counter: dict[str, int],
) -> list[ParsedKU]:
    """Extract knowledge units from one page of text."""
    results: list[ParsedKU] = []

    # Detect area header transitions
    area_code = current_area
    for line in text.splitlines():
        line = line.strip()
        m = _KA_HEADER_RE.match(line)
        if m and m.group("code") in _KNOWN_AREAS:
            area_code = m.group("code")

    if not area_code:
        return results

    # Look for knowledge unit entries: label + tier + hours on same/adjacent lines
    for m in _KU_RE.finditer(text):
        label = re.sub(r"\s+", " ", m.group("label")).strip()
        if len(label) < 5 or len(label) > 120:
            continue
        tier = m.group("tier").lower()
        hours = float(m.group("hours"))
        ku_counter[area_code] = ku_counter.get(area_code, 0) + 1
        ku_id = f"CS2023-{area_code}-KU-{ku_counter[area_code]}"
        results.append(
            ParsedKU(
                ku_id=ku_id,
                label=label,
                knowledge_area_code=area_code,
                tier=tier,
                contact_hours=hours,
            )
        )

    return results
