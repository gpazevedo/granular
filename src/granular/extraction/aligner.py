"""Aligner — runs the four-stage alignment pipeline for a single concept."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from granular.extraction.config import ExtractionConfig
from granular.extraction.embedder import Embedder
from granular.extraction.extractor import RawConcept
from granular.extraction.pipeline.reject import ConceptGraphSnapshot, reject
from granular.extraction.pipeline.rerank import _normalise_course_level, rerank
from granular.extraction.pipeline.retrieve import retrieve
from granular.extraction.pipeline.verify import verify
from granular.schema import (
    AlignmentStatus,
    Authority,
    Concept,
    Course,
    KnowledgeUnit,
    ProvenanceRecord,
)

logger = logging.getLogger(__name__)


class Aligner:
    """Runs stages 1–4 to produce an aligned Concept record."""

    def __init__(
        self,
        embedder: Embedder,
        ku_lookup: dict[str, KnowledgeUnit],
        config: ExtractionConfig,
        snapshot: Optional[ConceptGraphSnapshot] = None,
    ) -> None:
        self._embedder = embedder
        self._ku_lookup = ku_lookup
        self._config = config
        self._snapshot = snapshot or ConceptGraphSnapshot()

    def predict_area(self, raw: RawConcept, course: Course) -> Optional[str]:
        """First-pass, side-effect-free prediction of a concept's knowledge area.

        Runs retrieve + rerank (with no co-occurrence signal) and returns the
        knowledge area of the top candidate. Does NOT run reject/verify, does
        NOT record anything in the snapshot, and does NOT write to the graph.

        Used to seed the co-occurrence signal for the real alignment pass.
        Returns None if no candidate is found or on any failure.
        """
        try:
            candidates = retrieve(raw, self._embedder, self._config.top_k)
            ranked = rerank(
                raw, candidates, course, [], self._ku_lookup, self._config
            )
            if not ranked:
                return None
            top_ku = self._ku_lookup.get(ranked[0].ku_id)
            return top_ku.knowledge_area if top_ku else None
        except Exception as exc:
            logger.debug(
                "Area prediction failed for concept %r (%s): %s",
                raw.label,
                raw.source_course_id,
                exc,
            )
            return None

    def align(
        self,
        raw: RawConcept,
        course: Course,
        co_concept_areas: list[str],
    ) -> Concept:
        """Produce a Concept record for the given RawConcept.

        On any pipeline failure the concept is marked UNALIGNED, never dropped.
        """
        course_level = _normalise_course_level(course.course_number)
        concept_id = f"concept-{raw.source_course_id}-{uuid.uuid4().hex[:8]}"

        provenance = ProvenanceRecord(
            source_url=course.provenance.source_url,
            retrieved_at=datetime.now(tz=timezone.utc),
            adapter_name=self._config.adapter_name,
            adapter_version=self._config.adapter_version,
            source_revision=course.provenance.source_revision,
        )

        try:
            # Stage 1: Retrieve
            candidates = retrieve(raw, self._embedder, self._config.top_k)

            # Stage 2: Rerank
            ranked = rerank(
                raw, candidates, course, co_concept_areas, self._ku_lookup, self._config
            )

            # Stage 3: Reject
            reject_result = reject(raw, ranked, course_level, self._snapshot)

            # Stage 4: Verify
            alignment = verify(reject_result.surviving, self._config)

            # Record successful alignment in the snapshot
            if alignment.status == AlignmentStatus.ALIGNED and alignment.knowledge_unit_id:
                self._snapshot.record_alignment(alignment.knowledge_unit_id, course_level)

            # Confidence must be > 0 for schema (InferredFact requires [0,1]);
            # use a small floor for unaligned concepts so the record is valid.
            confidence = max(alignment.confidence, 0.01)

            return Concept(
                provenance=provenance,
                model_id=raw.model_id,
                confidence=confidence,
                concept_id=concept_id,
                authority=Authority.DERIVED,
                label=raw.label,
                source_course_id=raw.source_course_id,
                knowledge_unit_id=alignment.knowledge_unit_id,
                alignment_status=alignment.status,
            )

        except Exception as exc:
            logger.warning(
                "Alignment failed for concept %r (%s): %s",
                raw.label,
                raw.source_course_id,
                exc,
            )
            return Concept(
                provenance=provenance,
                model_id=raw.model_id,
                confidence=0.01,
                concept_id=concept_id,
                authority=Authority.DERIVED,
                label=raw.label,
                source_course_id=raw.source_course_id,
                knowledge_unit_id=None,
                alignment_status=AlignmentStatus.UNALIGNED,
            )
