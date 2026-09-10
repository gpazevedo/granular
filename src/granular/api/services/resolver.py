"""QueryResolver — plain-English query → CS2023 knowledge unit ids via pgvector."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ResolutionResult:
    ku_ids: list[str]
    model_id: str
    resolved: bool


class QueryResolver:
    """Resolves a plain-English query to CS2023 knowledge units.

    Never matches against course description text directly — all matching goes
    through the controlled vocabulary (pgvector KU embeddings).
    """

    def __init__(
        self,
        embedding_model_id: str,
        pgvector_dsn: str,
        top_k: int = 15,
        min_score: float = 0.3,
        llm_model_id: str = "",
    ) -> None:
        self._model_id = embedding_model_id
        self._dsn = pgvector_dsn
        self._top_k = top_k
        self._min_score = min_score
        self._llm_model_id = llm_model_id
        self._embedder = None
        self._llm = None

    def _get_embedder(self):
        if self._embedder is None:
            from granular.extraction.embedder import Embedder
            self._embedder = Embedder(self._model_id, self._dsn)
        return self._embedder

    def _get_llm(self):
        if self._llm is None:
            from granular.extraction.llm import get_provider
            self._llm = get_provider(self._llm_model_id)
        return self._llm

    def resolve(self, query: str) -> ResolutionResult:
        """Resolve a plain-English query to knowledge unit ids.

        Two stages:
          1. Retrieve — embed the query and pull top-k KU candidates above the
             similarity floor (favours recall; embedding similarity alone is
             noisy, e.g. "machine learning" matches "Machine-Level Representation").
          2. Rerank — an LLM inspects the candidate labels and keeps only those
             that genuinely match the student's intent (precision). Skipped when
             no LLM model is configured, falling back to embedding-only.
        """
        embedder = self._get_embedder()
        vector = embedder.embed_text(query)
        candidates = embedder.top_k_similar(vector, entity_type="knowledge_unit", k=self._top_k)

        scored = [(ku_id, label) for ku_id, label, score in candidates if score >= self._min_score]
        if not scored:
            return ResolutionResult(ku_ids=[], model_id=self._model_id, resolved=False)

        if not self._llm_model_id:
            return ResolutionResult(
                ku_ids=[k for k, _ in scored],
                model_id=self._model_id,
                resolved=True,
            )

        selected = self._llm_select(query, scored)
        # If the LLM returns nothing usable, fall back to the embedding candidates
        # rather than dropping to no_concepts_resolved on a valid query.
        if not selected:
            return ResolutionResult(
                ku_ids=[k for k, _ in scored],
                model_id=f"{self._model_id}+fallback",
                resolved=True,
            )

        return ResolutionResult(
            ku_ids=selected,
            model_id=f"{self._model_id}+{self._llm_model_id}",
            resolved=True,
        )

    def _llm_select(self, query: str, candidates: list[tuple[str, str]]) -> list[str]:
        """Ask the LLM which candidate KUs genuinely match the query intent.

        Returns the selected ku_ids in the LLM's ranked order. Never raises;
        returns [] on any failure so the caller can fall back.
        """
        import json

        from granular.extraction.llm import get_model_name

        numbered = "\n".join(
            f"{i}. {label} [{ku_id}]" for i, (ku_id, label) in enumerate(candidates)
        )
        valid_ids = {ku_id for ku_id, _ in candidates}

        system = (
            "You are a computer science curriculum advisor. A student describes "
            "what they want to learn. You are given candidate CS2023 knowledge "
            "units retrieved by embedding similarity, some of which are false "
            "matches (e.g. lexical overlap like 'machine learning' vs "
            "'machine-level representation'). Select ONLY the knowledge units "
            "that genuinely match the student's learning intent.\n"
            'Return JSON: {"ku_ids": ["...", "..."]} ordered most to least '
            "relevant. If none genuinely match, return an empty list."
        )
        user = f'Student interest: "{query}"\n\nCandidate knowledge units:\n{numbered}'

        try:
            raw = self._get_llm().chat_completion(
                system=system,
                user_message=user,
                model=get_model_name(self._llm_model_id),
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            parsed = json.loads(raw or "{}")
            ids = parsed.get("ku_ids", []) if isinstance(parsed, dict) else []
            # Keep only valid ids, preserve LLM order, dedupe.
            seen: set[str] = set()
            out: list[str] = []
            for k in ids:
                if isinstance(k, str) and k in valid_ids and k not in seen:
                    seen.add(k)
                    out.append(k)
            return out
        except Exception as exc:
            logger.warning("LLM query rerank failed for %r: %s", query, exc)
            return []
