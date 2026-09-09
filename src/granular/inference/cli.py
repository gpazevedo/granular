"""CLI entry point for granular-infer."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

from granular.inference.config import InferenceConfig, PipelineMode
from granular.inference.runner import InferenceRunner

# Load environment variables from a local .env file if present, so connection
# settings (NEO4J_*) are picked up without the caller having to export them.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is an optional convenience
    pass

app = typer.Typer(help="Infer concept-level dependency and similarity edges.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@app.command()
def run(
    config_path: Optional[Path] = typer.Option(None, "--config", help="TOML config file"),
    mode: str = typer.Option("full_pipeline", "--mode", help="Pipeline mode (ablation)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Score edges but do not write to Neo4j"),
    report: bool = typer.Option(False, "--report", help="Print KA coverage report and exit"),
) -> None:
    """Run the concept-graph-inference pipeline."""
    if config_path and config_path.exists():
        cfg = InferenceConfig.from_toml(config_path)
    else:
        cfg = InferenceConfig()
    cfg = InferenceConfig.from_env(cfg)
    cfg.mode = PipelineMode(mode)

    runner = InferenceRunner(cfg)
    summary = runner.run(dry_run=dry_run)

    if report:
        typer.echo("\nKnowledge Area Coverage:")
        for row in summary.knowledge_area_coverage:
            typer.echo(
                f"  {row.knowledge_area}: {row.concept_count} concepts, "
                f"{row.dependency_edge_count} deps, {row.similarity_edge_count} sims, "
                f"mean_conf={row.mean_confidence:.2f}"
            )

    typer.echo(
        f"\nInference complete: {summary.concepts_processed} concepts, "
        f"{summary.dependency_edges_inferred} dependency edges, "
        f"{summary.similarity_edges_inferred} similarity edges, "
        f"{summary.edges_rejected_cycle} cycle removals, "
        f"{summary.edges_rejected_ordering} ordering rejections."
    )

    if summary.rejection_rate() > cfg.rejection_threshold_pct:
        typer.echo(
            f"ERROR: rejection rate {summary.rejection_rate():.1f}% exceeds threshold",
            err=True,
        )
        raise typer.Exit(code=1)
