"""CLI entry point for granular-eval. (Task 11)"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

import typer

from granular.evaluation.config import EvalConfig
from granular.evaluation.graph_loader import Neo4jGraphLoader
from granular.evaluation.runner import EvalRunner

app = typer.Typer(help="Evaluate the concept-graph inference pipeline.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def _load_config(config_path: Optional[Path]) -> EvalConfig:
    if config_path and config_path.exists():
        cfg = EvalConfig.from_toml(config_path)
    else:
        cfg = EvalConfig()
    return EvalConfig.from_env(cfg)


@app.command()
def run(
    config_path: Optional[Path] = typer.Option(None, "--config", help="TOML config file"),
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Run identifier"),
    artefact_dir: Optional[Path] = typer.Option(None, "--artefact-dir", help="Artefact directory"),
) -> None:
    """Full evaluation run: split + metric + report."""
    cfg = _load_config(config_path)
    if artefact_dir:
        cfg.artefact_dir = artefact_dir

    loader = Neo4jGraphLoader(cfg.neo4j_uri, cfg.neo4j_user, cfg.neo4j_password)
    runner = EvalRunner(cfg, loader)
    result = runner.run(run_id=run_id or str(uuid.uuid4()))

    headline = result["headline"].get("all", {})
    typer.echo(
        f"\nEvaluation complete. Headline F1: {headline.get('f1', 0.0):.3f} "
        f"(P={headline.get('precision', 0.0):.3f}, R={headline.get('recall', 0.0):.3f})"
    )


@app.command()
def split(
    config_path: Optional[Path] = typer.Option(None, "--config", help="TOML config file"),
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Run identifier"),
) -> None:
    """Create held-out split only (run before granular-infer)."""
    typer.echo("Split creation requires a populated Neo4j graph. Use 'run' for the full flow.")
