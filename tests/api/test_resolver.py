"""Tests for QueryResolver LLM reranking, using fake embedder and LLM."""

from __future__ import annotations

import json

from granular.api.services.resolver import QueryResolver


class FakeEmbedder:
    """Returns a fixed candidate set regardless of the query vector."""

    def __init__(self, candidates: list[tuple[str, str, float]]) -> None:
        self._candidates = candidates

    def embed_text(self, text: str) -> list[float]:
        return [0.0]

    def top_k_similar(self, vector, entity_type, k):
        return self._candidates[:k]


class FakeLLM:
    def __init__(self, response: str) -> None:
        self._response = response
        self.calls = 0

    def chat_completion(self, system, user_message, model, temperature=0.0, response_format=None):
        self.calls += 1
        return self._response


def _resolver(embedder, llm=None, llm_model_id=""):
    r = QueryResolver(
        embedding_model_id="openai/text-embedding-3-small",
        pgvector_dsn="postgresql://x",
        top_k=15,
        min_score=0.3,
        llm_model_id=llm_model_id,
    )
    r._embedder = embedder
    if llm is not None:
        r._llm = llm
    return r


CANDIDATES = [
    ("KU-ML", "Machine Learning Foundations", 0.62),
    ("KU-AR", "Machine-Level Representation of Data", 0.55),  # lexical false match
    ("KU-AI", "Fundamentals of Artificial Intelligence", 0.51),
    ("KU-LOW", "Graphics Rendering", 0.20),  # below min_score, filtered pre-LLM
]


class TestEmbeddingOnly:
    def test_no_llm_returns_all_above_threshold(self):
        r = _resolver(FakeEmbedder(CANDIDATES), llm_model_id="")
        res = r.resolve("machine learning")
        assert res.resolved is True
        # KU-LOW filtered by min_score; the rest kept (no LLM filtering)
        assert res.ku_ids == ["KU-ML", "KU-AR", "KU-AI"]

    def test_nothing_above_threshold_unresolved(self):
        r = _resolver(FakeEmbedder([("KU-X", "X", 0.1)]), llm_model_id="")
        res = r.resolve("nonsense")
        assert res.resolved is False
        assert res.ku_ids == []


class TestLLMRerank:
    def test_llm_filters_lexical_false_matches(self):
        llm = FakeLLM(json.dumps({"ku_ids": ["KU-ML", "KU-AI"]}))
        r = _resolver(FakeEmbedder(CANDIDATES), llm=llm, llm_model_id="openai/gpt-4o")
        res = r.resolve("machine learning")
        assert res.ku_ids == ["KU-ML", "KU-AI"]  # KU-AR dropped
        assert "gpt-4o" in res.model_id
        assert llm.calls == 1

    def test_llm_order_preserved_and_invalid_ids_dropped(self):
        llm = FakeLLM(json.dumps({"ku_ids": ["KU-AI", "KU-ML", "KU-BOGUS"]}))
        r = _resolver(FakeEmbedder(CANDIDATES), llm=llm, llm_model_id="openai/gpt-4o")
        res = r.resolve("ai")
        assert res.ku_ids == ["KU-AI", "KU-ML"]  # bogus id not in candidate set

    def test_llm_empty_selection_falls_back_to_embeddings(self):
        llm = FakeLLM(json.dumps({"ku_ids": []}))
        r = _resolver(FakeEmbedder(CANDIDATES), llm=llm, llm_model_id="openai/gpt-4o")
        res = r.resolve("machine learning")
        assert res.ku_ids == ["KU-ML", "KU-AR", "KU-AI"]  # fallback
        assert "fallback" in res.model_id

    def test_llm_malformed_json_falls_back(self):
        llm = FakeLLM("not json")
        r = _resolver(FakeEmbedder(CANDIDATES), llm=llm, llm_model_id="openai/gpt-4o")
        res = r.resolve("machine learning")
        assert res.ku_ids == ["KU-ML", "KU-AR", "KU-AI"]  # fallback on parse failure
