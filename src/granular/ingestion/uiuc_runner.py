"""UiucRunner — static UIUC catalog ingestion.

UIUC's catalog is a single static page with all CS courses as <div class="courseblock">.
No Acalog, no bot mitigation, no pagination. One fetch, parse all, write output.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from granular.ingestion.adapters.uiuc.parser import UiucCourseBlock, parse_uiuc_catalog
from granular.ingestion.config import IngestConfig
from granular.ingestion.summary import IngestSummary
from granular.schema import (
    Authority,
    Course,
    CreditRange,
    DeclaredEdge,
    DeclaredEdgeType,
    PrerequisiteRule,
    ProgrammeLevel,
    ProvenanceRecord,
    SingleCourse,
    to_dict,
)

logger = logging.getLogger(__name__)

UIUC_CS_URL = "https://catalog.illinois.edu/courses-of-instruction/cs/"
UIUC_SUBJECT_URL = "https://catalog.illinois.edu/courses-of-instruction/{subject}/"


def _level_from_number(number: str) -> ProgrammeLevel:
    """UIUC: 500+ is graduate."""
    try:
        n = int(number)
        return ProgrammeLevel.GRADUATE if n >= 500 else ProgrammeLevel.UNDERGRADUATE
    except ValueError:
        return ProgrammeLevel.UNDERGRADUATE


# Prerequisite patterns in UIUC description prose
_PREREQ_PATTERNS = [
    re.compile(r"Prerequisite[:\s]+([^.]+)", re.IGNORECASE),
    re.compile(r"Prereq[:\s]+([^.]+)", re.IGNORECASE),
]
_COURSE_REF_RE = re.compile(r"\b([A-Z]{2,4})\s*(\d{3,4})\b")


def _extract_prereq_refs(description: str) -> list[str]:
    """Extract course references from prerequisite prose."""
    refs = []
    for pat in _PREREQ_PATTERNS:
        m = pat.search(description)
        if m:
            prereq_text = m.group(1)
            for cm in _COURSE_REF_RE.finditer(prereq_text):
                prefix, number = cm.group(1), cm.group(2)
                refs.append(f"{prefix}-{number}")
            break
    return list(dict.fromkeys(refs))


class UiucRunner:
    """UIUC static catalog ingestion.

    Fetches one or more subject catalog pages (each a single static HTML page
    of `courseblock` divs) and merges them into one output. Defaults to CS.
    """

    def __init__(self, config: IngestConfig, subjects: list[str] | None = None) -> None:
        self._config = config
        self._summary = IngestSummary()
        # Normalise to lowercase URL slugs; default to CS only.
        self._subjects = [s.strip().lower() for s in (subjects or ["cs"]) if s.strip()]

    def _fetch_subject(self, subject: str, ua: str) -> str | None:
        """Fetch a single subject catalog page. Returns HTML or None on failure."""
        url = UIUC_SUBJECT_URL.format(subject=subject)
        logger.info("Fetching UIUC catalog: %s", url)
        try:
            r = httpx.get(url, headers={"User-Agent": ua}, follow_redirects=True, timeout=60)
            r.raise_for_status()
            return r.text
        except httpx.HTTPStatusError as exc:
            logger.error("HTTP %d fetching UIUC %s catalog", exc.response.status_code, subject)
        except httpx.RequestError as exc:
            logger.error("Request error fetching UIUC %s catalog: %s", subject, exc)
        return None

    def run(self, dry_run: bool = False) -> IngestSummary:
        cfg = self._config
        cfg.output_dir.mkdir(parents=True, exist_ok=True)
        ua = cfg.user_agent

        # Fetch and parse every requested subject page.
        courses_blocks: list[UiucCourseBlock] = []
        for subject in self._subjects:
            html = self._fetch_subject(subject, ua)
            if html is None:
                continue
            url = UIUC_SUBJECT_URL.format(subject=subject)
            blocks = parse_uiuc_catalog(html, url)
            logger.info("Parsed %d %s course blocks from UIUC", len(blocks), subject.upper())
            courses_blocks.extend(blocks)

        logger.info(
            "Parsed %d total course blocks across %d subjects",
            len(courses_blocks),
            len(self._subjects),
        )

        if dry_run:
            logger.info("[dry-run] Would write %d courses", len(courses_blocks))
            self._summary.courses_attempted = len(courses_blocks)
            self._summary.finish()
            return self._summary

        courses: list[Course] = []
        edges: list[DeclaredEdge] = []

        for cb in courses_blocks:
            course, course_edges = self._build_course(cb)
            courses.append(course)
            edges.extend(course_edges)
            self._summary.courses_succeeded += 1
            for prereq in course.declared_prerequisites:
                if prereq.machine_checkable:
                    self._summary.prereqs_structured += 1
                else:
                    self._summary.prereqs_unstructured += 1

        self._summary.courses_attempted = len(courses_blocks)
        self._write_output(courses, edges, cfg.output_dir)
        self._summary.finish()
        self._summary.write(cfg.summary_path)
        return self._summary

    def _build_course(self, cb: UiucCourseBlock) -> tuple[Course, list[DeclaredEdge]]:
        course_id = f"{cb.prefix}-{cb.number}"
        now = datetime.now(tz=timezone.utc)
        provenance = ProvenanceRecord(
            source_url=cb.source_url,
            retrieved_at=now,
            adapter_name="uiuc_static",
            adapter_version=self._config.adapter_version,
            source_revision=None,
        )

        prereq_refs = _extract_prereq_refs(cb.description)
        prereq_rules: list[PrerequisiteRule] = []
        edges: list[DeclaredEdge] = []

        for i, ref_id in enumerate(prereq_refs):
            prereq_rules.append(
                PrerequisiteRule(
                    rule_id=f"prereq-{course_id}-{i}",
                    verbatim_text=f"Prerequisite: {ref_id}",
                    machine_checkable=True,
                    structured=SingleCourse(course_id=ref_id),
                )
            )
            edges.append(
                DeclaredEdge(
                    provenance=provenance,
                    edge_id=f"prereq-{course_id}-{ref_id}-{uuid.uuid4().hex[:8]}",
                    from_id=course_id,
                    to_id=ref_id,
                    relationship_type=DeclaredEdgeType.PREREQUISITE,
                )
            )

        course = Course(
            provenance=provenance,
            course_id=course_id,
            authority=Authority.DERIVED,
            subject_code=cb.prefix,
            course_number=cb.number,
            title=cb.title,
            description=cb.description,
            credits=cb.credits,
            level=_level_from_number(cb.number),
            cross_listings=[],
            declared_prerequisites=prereq_rules,
        )
        return course, edges

    def _write_output(self, courses: list[Course], edges: list[DeclaredEdge], output_dir: Path) -> None:
        with open(output_dir / "courses.jsonl", "w", encoding="utf-8") as f:
            for c in courses:
                f.write(json.dumps(to_dict(c), ensure_ascii=False) + "\n")
        with open(output_dir / "edges.jsonl", "w", encoding="utf-8") as f:
            for e in edges:
                f.write(json.dumps(to_dict(e), ensure_ascii=False) + "\n")
        (output_dir / "programmes.jsonl").write_text("", encoding="utf-8")
        logger.info("Wrote %d courses, %d edges to %s", len(courses), len(edges), output_dir)
