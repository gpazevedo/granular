"""Stage 2: Rerank on metadata.

Reranks retrieved candidates using signals the embedding does not carry:
- co-occurrence with neighbouring concepts (strongest signal)
- normalised course level as a depth proxy
- department as a soft prior only (never a hard filter)

Invariant: department is never used to zero-out or exclude a candidate.
"""

from __future__ import annotations

from dataclasses import dataclass

from granular.extraction.config import ExtractionConfig
from granular.extraction.extractor import RawConcept
from granular.extraction.pipeline.retrieve import CandidateKU
from granular.schema import Course, KnowledgeTier, KnowledgeUnit


@dataclass
class RankedCandidateKU:
    ku_id: str
    label: str
    similarity_score: float   # original, from retrieval
    rerank_score: float       # combined reranked score


def _normalise_course_level(course_number: str) -> float:
    """Normalise a Purdue course number (100–699) to [0, 1]."""
    try:
        # First digit indicates level: 1xxxx=100-level ... 6xxxx=600-level
        first = int(course_number[:1])
    except (ValueError, IndexError):
        return 0.5
    # Map 1..6 to 0..1
    return max(0.0, min(1.0, (first - 1) / 5.0))


def _ku_depth_proxy(tier: KnowledgeTier) -> float:
    """Estimate KU depth from tier: core concepts tend to be foundational."""
    return 0.3 if tier == KnowledgeTier.CORE else 0.7


def rerank(
    concept: RawConcept,
    candidates: list[CandidateKU],
    course: Course,
    co_concept_areas: list[str],   # knowledge areas of co-occurring concepts (best guess)
    ku_lookup: dict[str, KnowledgeUnit],
    config: ExtractionConfig,
) -> list[RankedCandidateKU]:
    """Rerank candidates. Returns sorted by rerank_score descending.

    Department is applied only as a small soft prior — never a hard filter.
    """
    course_level = _normalise_course_level(course.course_number)
    ranked: list[RankedCandidateKU] = []

    for cand in candidates:
        ku = ku_lookup.get(cand.ku_id)

        # Co-occurrence signal: does this candidate's area match co-concept areas?
        cooccurrence = 0.0
        if ku and co_concept_areas:
            matches = sum(1 for area in co_concept_areas if area == ku.knowledge_area)
            cooccurrence = matches / len(co_concept_areas)

        # Level proximity signal
        level_proximity = 0.0
        if ku:
            depth = _ku_depth_proxy(ku.tier)
            level_proximity = 1.0 - abs(course_level - depth)

        # Department soft prior: small boost, never a filter
        department_prior = 0.05  # constant small positive; does not exclude anything

        rerank_score = (
            config.weight_similarity * cand.similarity_score
            + config.weight_cooccurrence * cooccurrence
            + config.weight_level_proximity * level_proximity
            + config.weight_department_prior * department_prior
        )

        ranked.append(
            RankedCandidateKU(
                ku_id=cand.ku_id,
                label=cand.label,
                similarity_score=cand.similarity_score,
                rerank_score=rerank_score,
            )
        )

    ranked.sort(key=lambda r: r.rerank_score, reverse=True)
    return ranked
