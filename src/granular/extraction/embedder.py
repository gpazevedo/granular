"""Embedder — text → vector, stored in pgvector.

Critical invariant: only bare label text is embedded.
No course number, department, or level metadata is appended.
Metadata is used exclusively at the reranking stage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from granular.extraction.llm import get_model_name, get_provider

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536  # text-embedding-3-small default


@dataclass
class EmbeddingRecord:
    id: str
    entity_type: str  # "concept" or "knowledge_unit"
    label: str
    vector: list[float]
    model_id: str


class Embedder:
    """Wraps the embedding API and stores results in PostgreSQL.

    Note: Anthropic does not provide embeddings. If using Claude for extraction,
    embeddings must come from OpenAI (text-embedding-3-small) configured separately.
    """

    def __init__(self, model_id: str, pgvector_dsn: str) -> None:
        self._model_id = model_id
        self._dsn = pgvector_dsn
        self._provider = get_provider(model_id)
        self._conn = None

    def _get_conn(self):
        if self._conn is None:
            try:
                import psycopg2
                self._conn = psycopg2.connect(self._dsn)
            except ImportError:
                raise ImportError("psycopg2-binary required: pip install psycopg2-binary")
        return self._conn

    def embed_text(self, text: str) -> list[float]:
        """Embed bare label text. No metadata appended — invariant enforced here."""
        model = get_model_name(self._model_id)
        return self._provider.embedding(text, model)

    def store(self, record: EmbeddingRecord) -> None:
        """Upsert an embedding record into pgvector."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO embeddings (id, entity_type, label, vector, model_id)
                VALUES (%s, %s, %s, %s::vector, %s)
                ON CONFLICT (id) DO UPDATE SET
                    vector = EXCLUDED.vector,
                    model_id = EXCLUDED.model_id,
                    label = EXCLUDED.label
                """,
                (
                    record.id,
                    record.entity_type,
                    record.label,
                    str(record.vector),
                    record.model_id,
                ),
            )
        conn.commit()

    def embed_and_store(self, id: str, entity_type: str, label: str) -> list[float]:
        """Embed a label and store the result. Returns the vector."""
        vector = self.embed_text(label)
        self.store(
            EmbeddingRecord(
                id=id,
                entity_type=entity_type,
                label=label,
                vector=vector,
                model_id=self._model_id,
            )
        )
        return vector

    def top_k_similar(
        self,
        query_vector: list[float],
        entity_type: str,
        k: int,
    ) -> list[tuple[str, str, float]]:
        """Return top-k (id, label, similarity) for the given entity type."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, label, 1 - (vector <=> %s::vector) AS similarity
                FROM embeddings
                WHERE entity_type = %s
                ORDER BY vector <=> %s::vector
                LIMIT %s
                """,
                (str(query_vector), entity_type, str(query_vector), k),
            )
            return [(row[0], row[1], float(row[2])) for row in cur.fetchall()]

    def exists(self, id: str) -> bool:
        """Check if an embedding exists for the given id."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM embeddings WHERE id = %s", (id,))
            return cur.fetchone() is not None

    def close(self) -> None:
        if self._conn:
            self._conn.close()
