"""JudgementSetBuilder and JudgementAnalyser — blinded expert judgement. (Task 6)"""

from __future__ import annotations

import json
import logging
import random
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from math import floor
from pathlib import Path

from granular.evaluation.artefacts import ArtefactStore
from granular.evaluation.config import EvalConfig

logger = logging.getLogger(__name__)

RUBRIC_TEXT = """\
## Judgement rubric

For each item, assess whether concept A depends on concept B
(i.e. understanding B is necessary to understand A):

- correct: the dependency is real and directionally accurate
- plausible_but_wrong: dependency exists but direction is reversed, or the
  relationship is similarity rather than dependency
- incorrect: no meaningful dependency exists between these concepts
"""

VALID_LABELS = {"correct", "plausible_but_wrong", "incorrect"}


@dataclass
class JudgementItem:
    item_id: str
    concept_a_label: str
    concept_a_course: str
    concept_b_label: str
    concept_b_course: str
    knowledge_area: str
    # deliberately NO is_inferred, NO confidence — blind


@dataclass
class JudgementSet:
    items: list[JudgementItem]
    seed: int
    sample_size: int
    distractor_count: int


@dataclass
class CandidateEdge:
    """An inferred edge or distractor to be judged (internal, with labels)."""

    item_id: str
    concept_a_label: str
    concept_a_course: str
    concept_b_label: str
    concept_b_course: str
    knowledge_area: str
    is_inferred: bool
    confidence: float


@dataclass
class JudgementReport:
    correct_count: int = 0
    plausible_but_wrong_count: int = 0
    incorrect_count: int = 0
    approval_by_confidence_band: dict[str, float] = field(default_factory=dict)


class JudgementSetBuilder:
    """Builds a blinded judgement set of novel edges mixed with distractors."""

    def build(
        self,
        novel_edges: list[CandidateEdge],
        distractors: list[CandidateEdge],
        sample_size: int,
        distractor_ratio: float,
        config: EvalConfig,
    ) -> JudgementSet:
        # Stratified sample of novel edges across knowledge areas
        by_area: dict[str, list[CandidateEdge]] = defaultdict(list)
        for e in novel_edges:
            by_area[e.knowledge_area].append(e)

        rng = random.Random(config.random_seed)
        sampled: list[CandidateEdge] = []
        areas = list(by_area.keys())
        if areas:
            per_area = max(1, sample_size // len(areas))
            for area in areas:
                pool = by_area[area]
                rng.shuffle(pool)
                sampled.extend(pool[:per_area])
        sampled = sampled[:sample_size]

        n_distractors = floor(len(sampled) * distractor_ratio)
        rng.shuffle(distractors)
        chosen_distractors = distractors[:n_distractors]

        combined = sampled + chosen_distractors
        rng.shuffle(combined)

        items = [
            JudgementItem(
                item_id=e.item_id,
                concept_a_label=e.concept_a_label,
                concept_a_course=e.concept_a_course,
                concept_b_label=e.concept_b_label,
                concept_b_course=e.concept_b_course,
                knowledge_area=e.knowledge_area,
            )
            for e in combined
        ]
        return JudgementSet(
            items=items,
            seed=config.random_seed,
            sample_size=len(sampled),
            distractor_count=len(chosen_distractors),
        )

    def write_rubric(self, store: ArtefactStore) -> None:
        """Write the rubric BEFORE any judgement items are shown."""
        store.write("rubric", RUBRIC_TEXT)

    def write_blind(self, judgement_set: JudgementSet, store: ArtefactStore) -> None:
        """Write the blinded judgement set (no labels, no confidence)."""
        payload = {
            "seed": judgement_set.seed,
            "sample_size": judgement_set.sample_size,
            "distractor_count": judgement_set.distractor_count,
            "items": [asdict(i) for i in judgement_set.items],
        }
        store.write("judgement_set_blind", payload)


class JudgementAnalyser:
    """Analyses a completed (labelled) judgement set against pipeline confidence."""

    def load_labels(self, labelled_path: Path) -> dict[str, str]:
        data = json.loads(Path(labelled_path).read_text(encoding="utf-8"))
        labels: dict[str, str] = {}
        for item in data.get("items", []):
            label = item.get("label")
            if label not in VALID_LABELS:
                raise ValueError(f"Invalid label {label!r} for item {item.get('item_id')}")
            labels[item["item_id"]] = label
        return labels

    def analyse(
        self,
        labels: dict[str, str],
        candidates: list[CandidateEdge],
        config: EvalConfig,
    ) -> JudgementReport:
        report = JudgementReport()
        band_correct: dict[str, int] = defaultdict(int)
        band_total: dict[str, int] = defaultdict(int)

        cand_by_id = {c.item_id: c for c in candidates}

        for item_id, label in labels.items():
            if label == "correct":
                report.correct_count += 1
            elif label == "plausible_but_wrong":
                report.plausible_but_wrong_count += 1
            else:
                report.incorrect_count += 1

            cand = cand_by_id.get(item_id)
            if cand and cand.is_inferred:
                band = config.confidence_band(cand.confidence)
                band_total[band] += 1
                if label == "correct":
                    band_correct[band] += 1

        for band in ("high", "medium", "low"):
            total = band_total.get(band, 0)
            report.approval_by_confidence_band[band] = (
                band_correct.get(band, 0) / total if total > 0 else 0.0
            )
        return report
