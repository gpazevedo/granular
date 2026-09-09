"""CLI entry point for granular-ingest."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import typer

from granular.ingestion.config import IngestConfig
from granular.ingestion.purdue_runner import PurdueRunner
from granular.ingestion.runner import IngestRunner
from granular.ingestion.snapshot import create_snapshot, verify_snapshot
from granular.ingestion.uiuc_runner import UiucRunner

app = typer.Typer(help="Ingest Purdue CS course catalogue from Modern Campus Acalog.")

DEFAULT_SNAPSHOT_ROOT = Path("data/snapshots")

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


@app.command()
def uiuc(
    config_path: Optional[Path] = typer.Option(None, "--config", help="TOML config file"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Output directory"),
    subjects: str = typer.Option(
        "cs", "--subjects", help="Comma-separated subject slugs, e.g. 'cs,math,ece,cse,stat'"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Count courses only; no output files"),
) -> None:
    """Ingest UIUC courses from static subject catalog pages.

    Each UIUC subject catalog is a single static HTML page of course blocks
    (no bot mitigation, no pagination). Pass multiple subjects to also ingest
    prerequisite target departments (MATH, ECE, ...) so downstream inference
    can recover cross-subject prerequisites.
    """
    if config_path and config_path.exists():
        cfg = IngestConfig.from_toml(config_path)
    else:
        cfg = IngestConfig()
    cfg = IngestConfig.from_env(cfg)
    if output_dir:
        cfg.output_dir = output_dir

    subject_list = [s.strip() for s in subjects.split(",") if s.strip()]
    runner = UiucRunner(cfg, subjects=subject_list)
    summary = runner.run(dry_run=dry_run)

    typer.echo(
        f"\nUIUC ingestion complete ({', '.join(s.upper() for s in subject_list)}): "
        f"{summary.courses_succeeded}/{summary.courses_attempted} courses, "
        f"{summary.prereqs_structured} structured prereqs."
    )


@app.command()
def purdue(
    config_path: Optional[Path] = typer.Option(None, "--config", help="TOML config file"),
    force: bool = typer.Option(False, "--force", help="Re-fetch all pages ignoring cache"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Output directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="List courses only; no canonical fetches"),
    limit: Optional[int] = typer.Option(None, "--limit", help="Cap number of courses (for testing)"),
) -> None:
    """Ingest Purdue CS via purdue.io OData + CS canonical syllabus pages.

    This is the working strategy after the Acalog HTML catalogue was found to be
    behind bot mitigation. OData provides the course spine; canonical pages
    provide descriptions and prerequisites where they exist.
    """
    if config_path and config_path.exists():
        cfg = IngestConfig.from_toml(config_path)
    else:
        cfg = IngestConfig()
    cfg = IngestConfig.from_env(cfg)

    if force:
        cfg.force_refetch = True
    if output_dir:
        cfg.output_dir = output_dir

    runner = PurdueRunner(cfg)
    summary = runner.run(dry_run=dry_run, limit=limit)

    typer.echo(
        f"\nPurdue ingestion complete: {summary.courses_succeeded}/{summary.courses_attempted} courses, "
        f"{summary.prereqs_structured} structured prereqs, "
        f"{len([s for s in summary.courses_skipped if s.reason == 'no_canonical_page'])} without canonical page, "
        f"{len(summary.courses_failed)} failed."
    )


@app.command()
def snapshot(
    name: str = typer.Argument(..., help="Snapshot name, e.g. 'purdue-2026-2027'"),
    output_dir: Path = typer.Option(
        Path("data/ingestion/output"), "--output-dir", help="Ingestion output to promote"
    ),
    snapshot_root: Path = typer.Option(
        DEFAULT_SNAPSHOT_ROOT, "--snapshot-root", help="Committed snapshot root"
    ),
    catalogue_year: Optional[str] = typer.Option(
        None, "--catalogue-year", help="Catalogue year label for the manifest"
    ),
) -> None:
    """Promote the latest ingestion output into a committed, reusable snapshot.

    Run this once after 'run' so Purdue is fetched only once. Downstream stages
    read the snapshot via 'granular-extract run --courses-file'.
    """
    try:
        snapshot_dir = create_snapshot(output_dir, snapshot_root, name, catalogue_year)
    except FileNotFoundError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Snapshot '{name}' created at {snapshot_dir}.\n"
        f"Commit it to reuse without re-fetching:\n"
        f"  git add {snapshot_dir}\n"
        f"Downstream: granular-extract run --courses-file {snapshot_dir / 'courses.jsonl'}"
    )


@app.command("verify-snapshot")
def verify_snapshot_cmd(
    name: str = typer.Argument(..., help="Snapshot name to verify"),
    snapshot_root: Path = typer.Option(
        DEFAULT_SNAPSHOT_ROOT, "--snapshot-root", help="Committed snapshot root"
    ),
) -> None:
    """Verify a snapshot's files match the checksums in its manifest."""
    if verify_snapshot(snapshot_root, name):
        typer.echo(f"Snapshot '{name}' verified: all checksums match.")
    else:
        typer.echo(f"Snapshot '{name}' FAILED verification.", err=True)
        raise typer.Exit(code=1)
