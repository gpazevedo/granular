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


def verify(
    candidates: list[RankedCandidateKU],
    config: ExtractionConfig,
) -> AlignmentResult:
    """Select the final alignment and compute confidence.

    Confidence is the winner's share of the top-two rerank scores, or a
    sigmoid of the sole survivor's score.
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
        runner_up = candidates[1]
        denom = winner.rerank_score + runner_up.rerank_score
        confidence = winner.rerank_score / denom if denom > 0 else 0.0

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
