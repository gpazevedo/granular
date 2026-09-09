"""CLI entry point for granular-ingest."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import typer

from granular.ingestion.config import IngestConfig
from granular.ingestion.runner import IngestRunner

app = typer.Typer(help="Ingest Purdue CS course catalogue from Modern Campus Acalog.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@app.command()
def run(
    config_path: Optional[Path] = typer.Option(None, "--config", help="TOML config file"),
    since: Optional[str] = typer.Option(None, "--since", help="ISO-8601 date; skip unchanged pages"),
    force: bool = typer.Option(False, "--force", help="Re-fetch all pages ignoring cache"),
    workers: int = typer.Option(1, "--workers", help="Parallel fetch workers"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Output directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Discover URLs only; no fetches or writes"),
) -> None:
    """Run the full ingestion pipeline."""
    if config_path and config_path.exists():
        cfg = IngestConfig.from_toml(config_path)
    else:
        cfg = IngestConfig()

    cfg = IngestConfig.from_env(cfg)

    if since:
        from datetime import date
        cfg.since_date = date.fromisoformat(since)
    if force:
        cfg.force_refetch = True
    if workers > 1:
        cfg.workers = workers
    if output_dir:
        cfg.output_dir = output_dir

    runner = IngestRunner(cfg)
    summary = runner.run(dry_run=dry_run)

    typer.echo(
        f"\nIngestion complete: {summary.courses_succeeded}/{summary.courses_attempted} courses, "
        f"{summary.programmes_ingested} programmes, "
        f"{len(summary.courses_failed)} failed, "
        f"{len(summary.courses_skipped)} skipped."
    )

    if summary.failure_rate() > cfg.failure_threshold_pct:
        typer.echo(
            f"ERROR: failure rate {summary.failure_rate():.1f}% exceeds threshold "
            f"{cfg.failure_threshold_pct:.1f}%",
            err=True,
        )
        raise typer.Exit(code=1)
