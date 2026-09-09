"""PurdueRunner — OData + CS canonical-syllabus ingestion strategy.

This is the working ingestion path for Purdue, after live investigation found
the Acalog HTML catalogue behind bot mitigation. See catalogue-ingestion
design "Source reality (revised after live investigation)".

Strategy:
  1. purdue.io OData → authoritative CS course list (number, title, credits)
  2. Per course, probe the CS canonical syllabus page for description + prereqs
  3. Courses with no canonical page get a structural-only record, flagged

Produces canonical schema Course + DeclaredEdge records and a run summary.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from granular.ingestion.adapters.cs_canonical.parser import (
    CanonicalCourse,
    course_number_to_slug,
    parse_canonical_page,
)
from granular.ingestion.adapters.purdue_io.client import (
    ODataCourse,
    ODataUnavailable,
    PurdueIoClient,
)
from granular.ingestion.config import IngestConfig
from granular.ingestion.http_client import FetchFailure, RateLimitedClient
from granular.ingestion.robots import RobotsCache
from granular.ingestion.summary import FailureRecord, IngestSummary, SkipRecord
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

CANONICAL_BASE = "https://www.cs.purdue.edu/academic-programs/courses/canonical"
CS_SUBDOMAIN = "https://www.cs.purdue.edu"


def _level_from_number(number: str) -> ProgrammeLevel:
    """Purdue: 50000+ is graduate."""
    try:
        return ProgrammeLevel.GRADUATE if int(number[:1]) >= 5 else ProgrammeLevel.UNDERGRADUATE
    except (ValueError, IndexError):
        return ProgrammeLevel.UNDERGRADUATE


class PurdueRunner:
    """OData + canonical-syllabus ingestion for Purdue CS."""

    def __init__(self, config: IngestConfig) -> None:
        self._config = config
        self._summary = IngestSummary()

    def run(self, dry_run: bool = False, limit: int | None = None) -> IngestSummary:
        cfg = self._config
        cfg.output_dir.mkdir(parents=True, exist_ok=True)

        # --- 1. OData course list (authoritative spine) ---
        odata_client = PurdueIoClient(cfg.purdue_io_base_url, cfg.subject_filter)
        try:
            odata_courses = odata_client.fetch_all()
        except ODataUnavailable as exc:
            logger.error("OData unavailable — cannot build course list: %s", exc)
            self._summary.finish()
            return self._summary

        # Deduplicate by course number (OData has multiple rows per variable-title course)
        by_number: dict[str, ODataCourse] = {}
        for oc in odata_courses:
            if oc.number and oc.number not in by_number:
                by_number[oc.number] = oc

        course_numbers = sorted(by_number.keys())
        if limit:
            course_numbers = course_numbers[:limit]
        self._summary.courses_attempted = len(course_numbers)
        logger.info("OData: %d unique CS course numbers", len(course_numbers))

        if dry_run:
            logger.info("[dry-run] Would enrich %d courses via canonical pages", len(course_numbers))
            self._summary.finish()
            return self._summary

        # --- 2. Robots + rate-limited client for the CS subdomain ---
        robots = RobotsCache(CS_SUBDOMAIN, cfg.user_agent)
        robots.load()

        courses: list[Course] = []
        edges: list[DeclaredEdge] = []

        with RateLimitedClient(
            user_agent=cfg.user_agent,
            requests_per_second=cfg.requests_per_second,
            cache_db_path=cfg.cache_db_path,
            since_date=cfg.since_date,
            force_refetch=cfg.force_refetch,
        ) as client:
            for number in course_numbers:
                oc = by_number[number]
                slug = course_number_to_slug(number)
                url = f"{CANONICAL_BASE}/{slug}.html"

                canonical: CanonicalCourse | None = None
                if robots.is_allowed(url):
                    result = client.get(url)
                    if isinstance(result, FetchFailure):
                        if result.status_code == 404:
                            self._summary.courses_skipped.append(
                                SkipRecord(url=url, reason="no_canonical_page")
                            )
                        else:
                            self._summary.courses_failed.append(
                                FailureRecord(url=url, reason=result.reason, status_code=result.status_code)
                            )
                    else:
                        canonical = parse_canonical_page(result.body, url)
                else:
                    self._summary.courses_skipped.append(
                        SkipRecord(url=url, reason="robots_disallowed")
                    )

                course, course_edges = self._build_course(oc, canonical, cfg)
                courses.append(course)
                edges.extend(course_edges)
                self._summary.courses_succeeded += 1

                for prereq in course.declared_prerequisites:
                    if prereq.machine_checkable:
                        self._summary.prereqs_structured += 1
                    else:
                        self._summary.prereqs_unstructured += 1

        self._write_output(courses, edges, cfg.output_dir)
        self._summary.finish()
        self._summary.write(cfg.summary_path)
        return self._summary

    def _build_course(
        self,
        oc: ODataCourse,
        canonical: CanonicalCourse | None,
        cfg: IngestConfig,
    ) -> tuple[Course, list[DeclaredEdge]]:
        course_id = f"CS-{oc.number}"
        now = datetime.now(tz=timezone.utc)

        # Provenance: OData for the record; canonical URL when description came from there
        source_url = (
            canonical.source_url
            if canonical and canonical.has_description
            else f"{cfg.purdue_io_base_url}/Courses"
        )
        provenance = ProvenanceRecord(
            source_url=source_url,
            retrieved_at=now,
            adapter_name="purdue_odata_canonical",
            adapter_version=cfg.adapter_version,
            source_revision=None,
        )

        description = canonical.description if canonical else ""
        title = (canonical.title if canonical and canonical.title else oc.title) or oc.number

        credits: float | CreditRange = oc.credit_hours if oc.credit_hours is not None else 0.0

        # Prerequisites from the canonical page
        prereq_rules: list[PrerequisiteRule] = []
        edges: list[DeclaredEdge] = []
        if canonical and canonical.prerequisite_refs:
            for i, ref_id in enumerate(canonical.prerequisite_refs):
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
            subject_code="CS",
            course_number=oc.number,
            title=title,
            description=description,
            credits=credits,
            level=_level_from_number(oc.number),
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
        # Empty programmes file for pipeline compatibility
        (output_dir / "programmes.jsonl").write_text("", encoding="utf-8")
        logger.info(
            "Wrote %d courses, %d edges to %s",
            len(courses),
            len(edges),
            output_dir,
        )
