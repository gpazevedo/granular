"""Alignment-precision evaluation.

Measures the precision of concept -> CS2023 knowledge-unit alignments: of the
concepts the pipeline aligned to a knowledge unit, what fraction genuinely
belong to that unit? An LLM judge scores a stratified sample, and precision is
reported overall and per knowledge area.

This is the metric that would have caught the "solar car construction ->
Software Construction" class of false positive. It complements the existing
prerequisite-recovery F1, which evaluates the dependency graph rather than the
alignment layer.
"""

from __future__ import annotations

import json
import logging
import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass
class AlignedConcept:
    concept_id: str
    concept_label: str
    course_id: str
    ku_id: str
    ku_label: str
    knowledge_area: str
    confidence: float


@dataclass
class AlignmentJudgement:
    concept_id: str
    knowledge_area: str
    belongs: bool


@dataclass
class AreaPrecision:
    knowledge_area: str
    judged: int
    correct: int

    @property
    def precision(self) -> float:
        return self.correct / self.judged if self.judged else 0.0


@dataclass
class AlignmentPrecisionReport:
    sample_size: int
    judged: int
    correct: int
    seed: int
    by_area: list[AreaPrecision] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.correct / self.judged if self.judged else 0.0

    def to_dict(self) -> dict:
        return {
            "sample_size": self.sample_size,
            "judged": self.judged,
            "correct": self.correct,
            "precision": round(self.precision, 4),
            "seed": self.seed,
            "by_area": [
                {
                    "knowledge_area": a.knowledge_area,
                    "judged": a.judged,
                    "correct": a.correct,
                    "precision": round(a.precision, 4),
                }
                for a in sorted(self.by_area, key=lambda x: x.knowledge_area)
            ],
        }


class AlignmentJudge(Protocol):
    def judge(self, concept_label: str, ku_label: str) -> bool:
        """Return True if the concept genuinely belongs to the knowledge unit."""
        ...


class LLMAlignmentJudge:
    """LLM-backed judge: does a concept genuinely belong to a CS2023 unit?"""

    def __init__(self, model_id: str) -> None:
        self._model_id = model_id
        self._provider = None

    def _get_provider(self):
        if self._provider is None:
            from granular.extraction.llm import get_provider
            self._provider = get_provider(self._model_id)
        return self._provider

    def judge(self, concept_label: str, ku_label: str) -> bool:
        from granular.extraction.llm import get_model_name

        system = (
            "You are a CS curriculum expert auditing an automated mapping. "
            "Given an extracted course concept and the CS2023 knowledge unit it "
            "was aligned to, decide if the concept is genuinely an instance of "
            "that knowledge unit's topic (not merely a surface word overlap). "
            'Respond with JSON: {"belongs": true|false}.'
        )
        user = f'Concept: "{concept_label}"\nCS2023 knowledge unit: "{ku_label}"'
        try:
            raw = self._get_provider().chat_completion(
                system=system,
                user_message=user,
                model=get_model_name(self._model_id),
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            parsed = json.loads(raw or "{}")
            return bool(parsed.get("belongs", False)) if isinstance(parsed, dict) else False
        except Exception as exc:  # pragma: no cover - judged as not-belongs on error
            logger.warning("Alignment judge failed for %r -> %r: %s", concept_label, ku_label, exc)
            return False


def sample_aligned_concepts(
    concepts: list[AlignedConcept],
    sample_size: int,
    seed: int,
) -> list[AlignedConcept]:
    """Stratified sample across knowledge areas so every area is represented."""
    by_area: dict[str, list[AlignedConcept]] = defaultdict(list)
    for c in concepts:
        by_area[c.knowledge_area].append(c)

    rng = random.Random(seed)
    areas = list(by_area.keys())
    if not areas:
        return []
    per_area = max(1, sample_size // len(areas))
    sampled: list[AlignedConcept] = []
    for area in areas:
        pool = by_area[area][:]
        rng.shuffle(pool)
        sampled.extend(pool[:per_area])
    rng.shuffle(sampled)
    return sampled[:sample_size] if len(sampled) > sample_size else sampled


def evaluate_alignment_precision(
    concepts: list[AlignedConcept],
    judge: AlignmentJudge,
    sample_size: int = 100,
    seed: int = 42,
) -> AlignmentPrecisionReport:
    """Judge a stratified sample of aligned concepts and report precision."""
    sample = sample_aligned_concepts(concepts, sample_size, seed)

    area_judged: dict[str, int] = defaultdict(int)
    area_correct: dict[str, int] = defaultdict(int)
    correct = 0
    for c in sample:
        belongs = judge.judge(c.concept_label, c.ku_label)
        area_judged[c.knowledge_area] += 1
        if belongs:
            correct += 1
            area_correct[c.knowledge_area] += 1

    by_area = [
        AreaPrecision(knowledge_area=area, judged=area_judged[area], correct=area_correct[area])
        for area in area_judged
    ]
    return AlignmentPrecisionReport(
        sample_size=len(sample),
        judged=len(sample),
        correct=correct,
        seed=seed,
        by_area=by_area,
    )
