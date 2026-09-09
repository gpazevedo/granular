"""FastAPI dependency injection for the advisory API."""

from __future__ import annotations

from functools import lru_cache

from granular.api.config import APIConfig
from granular.api.services.discover_service import DiscoverService
from granular.api.services.graph_queries import Neo4jQueryService
from granular.api.services.resolver import QueryResolver


@lru_cache(maxsize=1)
def get_config() -> APIConfig:
    return APIConfig.from_env()


@lru_cache(maxsize=1)
def get_graph_service() -> Neo4jQueryService:
    cfg = get_config()
    return Neo4jQueryService(cfg.neo4j_uri, cfg.neo4j_user, cfg.neo4j_password)


@lru_cache(maxsize=1)
def get_resolver() -> QueryResolver:
    cfg = get_config()
    return QueryResolver(
        embedding_model_id=cfg.embedding_model_id,
        pgvector_dsn=cfg.pgvector_dsn,
        top_k=cfg.resolution_top_k,
        min_score=cfg.resolution_min_score,
    )


def get_discover_service() -> DiscoverService:
    cfg = get_config()
    return DiscoverService(get_resolver(), get_graph_service(), cfg)
