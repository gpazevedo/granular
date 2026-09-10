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


def llm_confirms_alignment(
    concept_label: str,
    ku_label: str,
    provider,
    model_name: str,
) -> bool:
    """Ask an LLM whether `concept_label` genuinely belongs to CS2023 unit `ku_label`.

    Guards against embedding false positives where lexical overlap
    ("construction", "design", "analysis") maps unrelated concepts onto
    software-engineering units. Returns True to accept, False to reject.

    Never raises: on any error returns True (fail-open), so verification only
    ever removes clear false positives and never silently drops the pipeline's
    output on an LLM outage.
    """
    import json

    system = (
        "You are a CS curriculum expert validating an automated mapping. "
        "Given an extracted course concept and a candidate CS2023 knowledge "
        "unit, decide if the concept is genuinely an instance of that knowledge "
        "unit's topic. Reject mappings that only share surface words (e.g. "
        "'construction of solar cars' is NOT 'Software Construction'; "
        "'group presentations' is NOT 'Software Project Management'). "
        'Respond with JSON: {"belongs": true|false}.'
    )
    user = f'Concept: "{concept_label}"\nCS2023 knowledge unit: "{ku_label}"'
    try:
        raw = provider.chat_completion(
            system=system,
            user_message=user,
            model=model_name,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(raw or "{}")
        if isinstance(parsed, dict) and "belongs" in parsed:
            return bool(parsed["belongs"])
        return True
    except Exception:  # pragma: no cover - fail open on LLM/parse errors
        return True


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
