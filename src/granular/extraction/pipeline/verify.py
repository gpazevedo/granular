"""Stage 4: Verify — constrained selection among surviving candidates.

Selects the top-ranked surviving candidate and computes a confidence.
Below min_confidence → LOW_CONFIDENCE_UNALIGNED.
No survivors → UNALIGNED.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from granular.extraction.config import ExtractionConfig
from granular.extraction.pipeline.rerank import RankedCandidateKU
from granular.schema import AlignmentStatus


@dataclass
class AlignmentResult:
    knowledge_unit_id: Optional[str]
    confidence: float
    status: AlignmentStatus


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _margin_confidence(scores: list[float], temperature: float) -> float:
    """Winner's confidence as a temperature-scaled softmax over the top two
    rerank scores — i.e. the winner's separation from its strongest rival.

    Ranges in [0.5, 1.0]: a clear winner (large gap to the runner-up)
    approaches 1.0; a near-tie approaches 0.5. Using the top two rather than
    the whole field avoids diluting the winner across many similar candidates
    (with k=10, a softmax over all candidates crushes even a clear winner).

    `scores` must be sorted descending (verify passes ranked candidates).
    Uses the max-subtraction trick for numerical stability.
    """
    temp = temperature if temperature > 1e-6 else 1e-6
    top = scores[0]
    runner_up = scores[1]
    exp_winner = 1.0  # exp((top - top) / temp)
    exp_runner = math.exp((runner_up - top) / temp)
    total = exp_winner + exp_runner
    if total <= 0:
        return 0.0
    return exp_winner / total


def verify(
    candidates: list[RankedCandidateKU],
    config: ExtractionConfig,
) -> AlignmentResult:
    """Select the final alignment and compute confidence.

    Confidence is the winner's probability under a temperature-scaled softmax
    over the top-k rerank scores — a margin over the whole candidate field.
    With a single survivor, falls back to a sigmoid of its rerank score.
    """
    if not candidates:
        return AlignmentResult(
            knowledge_unit_id=None,
            confidence=0.0,
            status=AlignmentStatus.UNALIGNED,
        )

    winner = candidates[0]

    if len(candidates) == 1:
        confidence = _sigmoid(winner.rerank_score)
    else:
        scores = [c.rerank_score for c in candidates]
        confidence = _margin_confidence(scores, config.confidence_temperature)

    confidence = max(0.0, min(1.0, confidence))

    if confidence < config.min_confidence:
        return AlignmentResult(
            knowledge_unit_id=None,
            confidence=confidence,
            status=AlignmentStatus.LOW_CONFIDENCE_UNALIGNED,
        )

    return AlignmentResult(
        knowledge_unit_id=winner.ku_id,
        confidence=confidence,
        status=AlignmentStatus.ALIGNED,
    )
