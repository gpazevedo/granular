"""Stage 1: Retrieve — embed concept label, retrieve top-k KU candidates.

Embeddings do retrieval, never adjudication.
Only the bare label text is embedded — no metadata.
"""

from __future__ import annotations

from dataclasses import dataclass

from granular.extraction.embedder import Embedder
from granular.extraction.extractor import RawConcept


@dataclass
class CandidateKU:
    ku_id: str
    label: str
    similarity_score: float  # raw cosine similarity — carried for inspection only


def retrieve(
    concept: RawConcept,
    embedder: Embedder,
    top_k: int,
) -> list[CandidateKU]:
    """Embed the concept label and retrieve top-k KnowledgeUnit candidates.

    Returns candidates sorted by similarity descending.
    Similarity scores are informational — they never solely determine alignment.
    """
    # Embed the bare label only (invariant: no metadata appended)
    vector = embedder.embed_text(concept.label)
    results = embedder.top_k_similar(vector, entity_type="knowledge_unit", k=top_k)
    return [
        CandidateKU(ku_id=ku_id, label=label, similarity_score=score)
        for ku_id, label, score in results
    ]
