"""IngestRunner — orchestrates the full catalogue-ingestion pipeline."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from granular.ingestion.adapters.acalog.catalogue import AcalogCatalogueAdapter
from granular.ingestion.adapters.acalog.course_parser import parse_course_page
from granular.ingestion.adapters.acalog.programme_parser import parse_programme_page
from granular.ingestion.adapters.purdue_io.client import ODataUnavailable, PurdueIoClient
from granular.ingestion.adapters.purdue_io.mapper import cross_check
from granular.ingestion.config import IngestConfig
from granular.ingestion.http_client import FetchFailure, RateLimitedClient
from granular.ingestion.normaliser import NormaliserError, normalise_course, normalise_programme
from granular.ingestion.robots import RobotsCache
from granular.ingestion.summary import FailureRecord, IngestSummary, SkipRecord
from granular.schema import Course, DeclaredEdge, Programme, to_dict

logger = logging.getLogger(__name__)


class IngestRunner:
    """Top-level orchestrator for catalogue ingestion."""

    def __init__(self, config: IngestConfig) -> None:
        self._config = config
        self._summary = IngestSummary()

    def run(self, dry_run: bool = False) -> IngestSummary:
        cfg = self._config
        cfg.output_dir.mkdir(parents=True, exist_ok=True)

        robots = RobotsCache(cfg.catalogue_base_url, cfg.user_agent)
        robots.load()

        with RateLimitedClient(
            user_agent=cfg.user_agent,
            requests_per_second=cfg.requests_per_second,
            cache_db_path=cfg.cache_db_path,
            since_date=cfg.since_date,
            force_refetch=cfg.force_refetch,
        ) as client:
            adapter = AcalogCatalogueAdapter(
                base_url=cfg.catalogue_base_url,
                subject_filter=cfg.subject_filter,
                client=client,
                robots=robots,
            )

            # --- Discover catoid ---
            catoid = adapter.discover_catoid()
            if not catoid:
                logger.error("Could not discover catoid — aborting.")
                self._summary.finish()
                return self._summary

            # --- Discover course URLs ---
            course_urls = adapter.discover_course_urls(catoid)
            logger.info("Found %d course URLs", len(course_urls))

            if dry_run:
                programme_urls = adapter.discover_programme_urls(catoid)
                logger.info(
                    "[dry-run] Would fetch %d courses, %d programmes",
                    len(course_urls),
                    len(programme_urls),
                )
                self._summary.finish()
                return self._summary

            # --- Fetch OData (optional) ---
            odata_by_number: dict[str, object] = {}
            try:
                odata_client = PurdueIoClient(
                    base_url=cfg.purdue_io_base_url,
                    subject_filter=cfg.subject_filter,
                )
                odata_courses = odata_client.fetch_all()
                odata_by_number = {c.number: c for c in odata_courses}
                logger.info("OData: %d courses loaded for cross-checking", len(odata_by_number))
            except ODataUnavailable as exc:
                logger.warning("purdue.io OData unavailable (%s); continuing HTML-only", exc)
                self._summary.odata_fallback_used = True

            # --- Ingest courses ---
            courses: list[Course] = []
            edges: list[DeclaredEdge] = []

            def _fetch_and_parse(cu: object) -> tuple:
                url = cu.url  # type: ignore[attr-defined]
                if not robots.is_allowed(url):
                    return None, None, "robots_disallowed"
                result = client.get(url)
                if isinstance(result, FetchFailure):
                    return None, result, None
                raw = parse_course_page(result.body, url, source_revision=catoid)
                if raw is None:
                    return None, FetchFailure(url=url, status_code=200, reason="parse_failed"), None
                # Cross-check with OData
                odata = odata_by_number.get(raw.course_number)
                cross_check(raw.description, odata, url)  # logs discrepancies
                return raw, None, None

            self._summary.courses_attempted = len(course_urls)

            if cfg.workers > 1:
                with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
                    futures = {pool.submit(_fetch_and_parse, cu): cu for cu in course_urls}
                    for future in as_completed(futures):
                        cu = futures[future]
                        raw, failure, skip_reason = future.result()
                        self._process_course(raw, failure, skip_reason, cu.url, cfg, courses, edges)
            else:
                for cu in course_urls:
                    raw, failure, skip_reason = _fetch_and_parse(cu)
                    self._process_course(raw, failure, skip_reason, cu.url, cfg, courses, edges)

            # --- Ingest programmes ---
            programme_urls = adapter.discover_programme_urls(catoid)
            programmes: list[Programme] = []
            for pu in programme_urls:
                if not robots.is_allowed(pu.url):
                    self._summary.courses_skipped.append(
                        SkipRecord(url=pu.url, reason="robots_disallowed")
                    )
                    continue
                result = client.get(pu.url)
                if isinstance(result, FetchFailure):
                    logger.warning("Programme fetch failed: %s — %s", pu.url, result.reason)
                    continue
                raw_prog = parse_programme_page(result.body, pu.url, source_revision=catoid)
                if raw_prog:
                    try:
                        prog = normalise_programme(raw_prog, cfg)
                        programmes.append(prog)
                    except Exception as exc:
                        logger.warning("Programme normalisation failed for %s: %s", pu.url, exc)

            self._summary.programmes_ingested = len(programmes)

            # --- Write output ---
            self._write_output(courses, edges, programmes, cfg.output_dir)

        self._summary.finish()
        self._summary.write(cfg.summary_path)

        # Exit check
        if self._summary.failure_rate() > cfg.failure_threshold_pct:
            logger.error(
                "Failure rate %.1f%% exceeds threshold %.1f%%",
                self._summary.failure_rate(),
                cfg.failure_threshold_pct,
            )

        return self._summary

    def _process_course(
        self,
        raw: object,
        failure: Optional[FetchFailure],
        skip_reason: Optional[str],
        url: str,
        cfg: IngestConfig,
        courses: list,
        edges: list,
    ) -> None:
        if skip_reason:
            self._summary.courses_skipped.append(SkipRecord(url=url, reason=skip_reason))
            return
        if failure:
            self._summary.courses_failed.append(
                FailureRecord(url=url, reason=failure.reason, status_code=failure.status_code)
            )
            return
        try:
            course, course_edges = normalise_course(raw, cfg)  # type: ignore[arg-type]
            courses.append(course)
            edges.extend(course_edges)
            self._summary.courses_succeeded += 1
            # Count structured vs. unstructured prereqs
            for prereq in course.declared_prerequisites:
                if prereq.machine_checkable:
                    self._summary.prereqs_structured += 1
                else:
                    self._summary.prereqs_unstructured += 1
        except NormaliserError as exc:
            logger.warning("Normalisation failed for %s: %s", url, exc)
            self._summary.courses_failed.append(
                FailureRecord(url=url, reason=str(exc))
            )

    def _write_output(
        self,
        courses: list[Course],
        edges: list[DeclaredEdge],
        programmes: list[Programme],
        output_dir: Path,
    ) -> None:
        courses_path = output_dir / "courses.jsonl"
        edges_path = output_dir / "edges.jsonl"
        programmes_path = output_dir / "programmes.jsonl"

        with open(courses_path, "w", encoding="utf-8") as f:
            for course in courses:
                f.write(json.dumps(to_dict(course), ensure_ascii=False) + "\n")
        logger.info("Wrote %d courses to %s", len(courses), courses_path)

        with open(edges_path, "w", encoding="utf-8") as f:
            for edge in edges:
                f.write(json.dumps(to_dict(edge), ensure_ascii=False) + "\n")
        logger.info("Wrote %d edges to %s", len(edges), edges_path)

        with open(programmes_path, "w", encoding="utf-8") as f:
            for prog in programmes:
                f.write(json.dumps(to_dict(prog), ensure_ascii=False) + "\n")
        logger.info("Wrote %d programmes to %s", len(programmes), programmes_path)
