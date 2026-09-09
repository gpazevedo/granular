"""ExtractionRunner — orchestrates the per-course concept extraction + alignment loop."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from granular.extraction.aligner import Aligner
from granular.extraction.bootstrap.seed_writer import load_seed
from granular.extraction.config import ExtractionConfig
from granular.extraction.coverage import CoverageIndex
from granular.extraction.embedder import Embedder
from granular.extraction.extractor import ConceptExtractor
from granular.extraction.graph_writer import GraphWriter
from granular.extraction.pipeline.reject import ConceptGraphSnapshot
from granular.extraction.summary import ExtractionSummary
from granular.schema import (
    AlignmentStatus,
    Concept,
    Course,
    CreditRange,
    KnowledgeUnit,
    ProgrammeLevel,
    ProvenanceRecord,
)

logger = logging.getLogger(__name__)


def _course_from_dict(d: dict) -> Course:
    """Reconstruct a Course from a serialised ingestion record."""
    prov = d["provenance"]
    from datetime import datetime

    provenance = ProvenanceRecord(
        source_url=prov["source_url"],
        retrieved_at=datetime.fromisoformat(prov["retrieved_at"]),
        adapter_name=prov["adapter_name"],
        adapter_version=prov["adapter_version"],
        source_revision=prov.get("source_revision"),
    )
    credits = d["credits"]
    if isinstance(credits, dict):
        credits = CreditRange(credits["min_credits"], credits["max_credits"])

    from granular.schema import Authority

    return Course(
        provenance=provenance,
        course_id=d["course_id"],
        authority=Authority(d["authority"]),
        subject_code=d["subject_code"],
        course_number=d["course_number"],
        title=d["title"],
        description=d["description"],
        credits=credits,
        level=ProgrammeLevel(d["level"]),
        cross_listings=d.get("cross_listings", []),
        declared_prerequisites=[],  # not needed for extraction
    )


class ExtractionRunner:
    """Orchestrates concept extraction and alignment across all ingested courses."""

    def __init__(self, config: ExtractionConfig) -> None:
        self._config = config
        self._summary = ExtractionSummary()

    def run(
        self,
        courses_path: Path,
        force: bool = False,
        dry_run: bool = False,
        course_subset: Optional[list[str]] = None,
    ) -> ExtractionSummary:
        cfg = self._config

        # Load CS2023 vocabulary
        knowledge_units = load_seed(cfg.vocabulary_path)
        ku_lookup: dict[str, KnowledgeUnit] = {ku.ku_id: ku for ku in knowledge_units}
        logger.info("Loaded %d knowledge units from %s", len(knowledge_units), cfg.vocabulary_path)

        # Load courses
        courses = self._load_courses(courses_path, course_subset)
        logger.info("Loaded %d courses for extraction", len(courses))

        embedder = Embedder(cfg.embedding_model_id, cfg.pgvector_dsn)
        graph = GraphWriter(cfg.neo4j_uri, cfg.neo4j_user, cfg.neo4j_password)
        extractor = ConceptExtractor(cfg.llm_model_id)

        # Embed all KU labels (idempotent — skip if already present)
        if not dry_run:
            for ku in knowledge_units:
                if force or not embedder.exists(ku.ku_id):
                    embedder.embed_and_store(ku.ku_id, "knowledge_unit", ku.label)
                graph.write_knowledge_unit(ku)

        snapshot = ConceptGraphSnapshot()
        aligner = Aligner(embedder, ku_lookup, cfg, snapshot)
        all_concepts: list[Concept] = []
        confidences: list[float] = []

        for course in courses:
            self._summary.courses_processed += 1

            if not course.description or len(course.description.strip()) < cfg.min_description_length:
                self._summary.concepts_skipped_empty += 1
                logger.debug("Skipping %s: description too short", course.course_id)
                continue

            raw_concepts = extractor.extract(course.course_id, course.description)
            self._summary.concepts_extracted += len(raw_concepts)

            if dry_run:
                continue

            # Pass 1: predict the knowledge area of each concept (no side effects),
            # so the co-occurrence signal can be seeded from sibling concepts.
            predicted_areas: list[Optional[str]] = [
                aligner.predict_area(raw, course) for raw in raw_concepts
            ]

            for idx, raw in enumerate(raw_concepts):
                if not force and graph.concept_exists(course.course_id, raw.label):
                    continue
                # Co-occurring areas = predicted areas of the OTHER concepts in
                # this course (a concept should not reinforce itself).
                co_areas = [
                    area
                    for j, area in enumerate(predicted_areas)
                    if j != idx and area
                ]
                concept = aligner.align(raw, course, co_areas)
                all_concepts.append(concept)
                confidences.append(concept.confidence)

                if concept.alignment_status == AlignmentStatus.ALIGNED:
                    self._summary.concepts_aligned += 1
                elif concept.alignment_status == AlignmentStatus.LOW_CONFIDENCE_UNALIGNED:
                    self._summary.concepts_low_confidence += 1
                else:
                    self._summary.concepts_unaligned += 1

                graph.write_concept(concept)
                embedder.embed_and_store(concept.concept_id, "concept", concept.label)

        # Build coverage index
        if not dry_run:
            coverage = CoverageIndex()
            coverage.build(all_concepts)
            thin = coverage.thin_coverage_units(min_courses=1)
            logger.info("Coverage: %d thin-coverage knowledge units", len(thin))

        self._summary.compute_confidence_stats(confidences)
        self._summary.finish()
        if not dry_run:
            self._summary.write(cfg.summary_path)

        embedder.close()
        graph.close()
        return self._summary

    def _load_courses(
        self,
        courses_path: Path,
        subset: Optional[list[str]],
    ) -> list[Course]:
        courses: list[Course] = []
        with open(courses_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if subset and d["course_id"] not in subset:
                    continue
                try:
                    courses.append(_course_from_dict(d))
                except Exception as exc:
                    logger.warning("Could not load course %s: %s", d.get("course_id"), exc)
        return courses
