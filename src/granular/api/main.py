"""FastAPI application entry point for the advisory query backend."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from granular.api.config import APIConfig
from granular.api.routers import discover

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def create_app(config: APIConfig | None = None) -> FastAPI:
    cfg = config or APIConfig.from_env()

    app = FastAPI(
        title="Granular Advisory API",
        description="Interest-driven discovery over the Purdue CS knowledge map.",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[cfg.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(discover.router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
