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
    ) -> None:
        self._model_id = embedding_model_id
        self._dsn = pgvector_dsn
        self._top_k = top_k
        self._min_score = min_score
        self._embedder = None

    def _get_embedder(self):
        if self._embedder is None:
            from granular.extraction.embedder import Embedder
            self._embedder = Embedder(self._model_id, self._dsn)
        return self._embedder

    def resolve(self, query: str) -> ResolutionResult:
        """Resolve a plain-English query to knowledge unit ids.

        Embeds the bare query text, retrieves top-k KU candidates, filters by
        min score. Returns resolved=False if nothing clears the threshold.
        """
        embedder = self._get_embedder()
        vector = embedder.embed_text(query)
        candidates = embedder.top_k_similar(vector, entity_type="knowledge_unit", k=self._top_k)

        ku_ids = [ku_id for ku_id, _label, score in candidates if score >= self._min_score]

        return ResolutionResult(
            ku_ids=ku_ids,
            model_id=self._model_id,
            resolved=len(ku_ids) > 0,
        )
