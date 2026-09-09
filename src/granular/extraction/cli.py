"""CLI entry point for granular-extract."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

from granular.extraction.bootstrap.pdf_parser import parse_cs2023_pdf
from granular.extraction.bootstrap.seed_writer import build_knowledge_units, write_seed
from granular.extraction.config import ExtractionConfig
from granular.extraction.runner import ExtractionRunner

app = typer.Typer(help="Extract concepts from Purdue CS courses and align to CS2023.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@app.command()
def bootstrap(
    pdf_path: Path = typer.Argument(..., help="Path to the CS2023 PDF"),
    output: Path = typer.Option(
        Path("data/cs2023_vocabulary.json"), "--output", help="Seed file output path"
    ),
) -> None:
    """One-time: extract CS2023 knowledge units from the PDF into a seed file."""
    parsed = parse_cs2023_pdf(str(pdf_path))
    units = build_knowledge_units(parsed)
    write_seed(units, output)
    typer.echo(f"Bootstrap complete: {len(units)} knowledge units written to {output}")


@app.command()
def run(
    courses: Path = typer.Option(
        Path("data/ingestion/output/courses.jsonl"), "--courses-file", help="Ingested courses JSONL"
    ),
    config_path: Optional[Path] = typer.Option(None, "--config", help="TOML config file"),
    force: bool = typer.Option(False, "--force", help="Re-extract all courses"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Extract but do not write to Neo4j"),
    course_ids: Optional[str] = typer.Option(None, "--course-ids", help="Comma-separated subset"),
) -> None:
    """Run concept extraction + alignment on ingested courses."""
    if config_path and config_path.exists():
        cfg = ExtractionConfig.from_toml(config_path)
    else:
        cfg = ExtractionConfig()
    cfg = ExtractionConfig.from_env(cfg)

    subset = course_ids.split(",") if course_ids else None

    runner = ExtractionRunner(cfg)
    summary = runner.run(courses, force=force, dry_run=dry_run, course_subset=subset)

    typer.echo(
        f"\nExtraction complete: {summary.courses_processed} courses, "
        f"{summary.concepts_extracted} concepts extracted, "
        f"{summary.concepts_aligned} aligned, "
        f"{summary.concepts_unaligned} unaligned, "
        f"{summary.concepts_low_confidence} low-confidence."
    )


@app.command()
def coverage(
    config_path: Optional[Path] = typer.Option(None, "--config", help="TOML config file"),
) -> None:
    """Print a coverage report for the current graph (requires Neo4j)."""
    typer.echo("Coverage reporting requires a populated Neo4j graph. Run 'run' first.")
