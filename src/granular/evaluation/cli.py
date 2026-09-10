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

# Load environment variables from a local .env file if present, so connection
# settings (NEO4J_*) are picked up without the caller having to export them.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is an optional convenience
    pass

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
def ablation(
    config_path: Optional[Path] = typer.Option(None, "--config", help="TOML config file"),
) -> None:
    """Real ablation: run inference in retrieval_only / retrieval_rerank /
    full_pipeline modes and report distinct held-out F1 for each.

    This re-runs scoring in-memory for each mode, so it takes a few minutes.
    """
    import json as _json

    from granular.evaluation.ablation import AblationRunner, build_ablation_infer_fn
    from granular.evaluation.split import HeldOutSplit
    from granular.inference.config import InferenceConfig as InfConfig

    cfg = _load_config(config_path)
    loader = Neo4jGraphLoader(cfg.neo4j_uri, cfg.neo4j_user, cfg.neo4j_password)

    # Load graph + declared prereqs + concepts for scoring.
    graph, all_declared = loader()
    concepts_raw = loader.load_concepts_for_ablation()
    if not concepts_raw:
        typer.echo("No concepts found. Run extraction first.", err=True)
        raise typer.Exit(code=1)

    # Build held-out split
    prereq_keys = [f"{a}->{b}" for (a, b) in sorted(all_declared)]
    split = HeldOutSplit().create(prereq_keys, cfg)
    held_out = [(a, b) for k in split.test for a, b in [k.split("->", 1)]]

    # Build the inference config (reads .env for Neo4j etc).
    inf_cfg = InfConfig()
    from granular.inference.config import InferenceConfig
    inf_cfg = InferenceConfig.from_env(inf_cfg)

    infer_fn = build_ablation_infer_fn(concepts_raw, all_declared, inf_cfg)
    runner = AblationRunner(cfg, infer_fn)
    report = runner.run_all(held_out, all_declared)

    out_dir = cfg.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "retrieval_only": {"f1": report.retrieval_only.f1, "precision": report.retrieval_only.precision, "recall": report.retrieval_only.recall},
        "retrieval_rerank": {"f1": report.retrieval_rerank.f1, "precision": report.retrieval_rerank.precision, "recall": report.retrieval_rerank.recall},
        "full_pipeline": {"f1": report.full_pipeline.f1, "precision": report.full_pipeline.precision, "recall": report.full_pipeline.recall},
    }
    (out_dir / "ablation.json").write_text(_json.dumps(result, indent=2), encoding="utf-8")

    typer.echo("\nAblation results:")
    for mode, m in [
        ("retrieval_only", report.retrieval_only),
        ("retrieval_rerank", report.retrieval_rerank),
        ("full_pipeline", report.full_pipeline),
    ]:
        typer.echo(f"  {mode:20s} P={m.precision:.3f} R={m.recall:.3f} F1={m.f1:.3f}")


@app.command()
def alignment(
    config_path: Optional[Path] = typer.Option(None, "--config", help="TOML config file"),
    sample_size: int = typer.Option(100, "--sample-size", help="Concepts to judge"),
    judge_model: str = typer.Option(
        "openai/gpt-4o", "--judge-model", help="LLM judge model id"
    ),
) -> None:
    """Alignment-precision eval: LLM-judge whether aligned concepts truly belong
    to their CS2023 knowledge unit; report precision overall and per area.
    """
    import json as _json

    from granular.evaluation.alignment_eval import (
        LLMAlignmentJudge,
        evaluate_alignment_precision,
    )

    cfg = _load_config(config_path)
    loader = Neo4jGraphLoader(cfg.neo4j_uri, cfg.neo4j_user, cfg.neo4j_password)
    concepts = loader.load_aligned_concepts()
    if not concepts:
        typer.echo("No aligned concepts found. Run extraction first.", err=True)
        raise typer.Exit(code=1)

    judge = LLMAlignmentJudge(judge_model)
    report = evaluate_alignment_precision(
        concepts, judge, sample_size=sample_size, seed=cfg.random_seed
    )

    out_dir = cfg.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "alignment_precision.json").write_text(
        _json.dumps(report.to_dict(), indent=2), encoding="utf-8"
    )

    typer.echo(
        f"\nAlignment precision: {report.precision:.3f} "
        f"({report.correct}/{report.judged} judged correct)"
    )
    typer.echo("By knowledge area:")
    for a in sorted(report.by_area, key=lambda x: x.precision):
        typer.echo(f"  {a.knowledge_area}: {a.precision:.3f} ({a.correct}/{a.judged})")


@app.command()
def discover(
    config_path: Optional[Path] = typer.Option(None, "--config", help="TOML config file"),
    labels_path: Path = typer.Option(
        Path("data/evaluation/discover_labels.json"), "--labels", help="Labelled queries"
    ),
    vocabulary_path: Path = typer.Option(
        Path("data/cs2023_vocabulary.json"), "--vocabulary", help="CS2023 seed for ku->area"
    ),
) -> None:
    """Discover-relevance eval: resolve labelled queries and score whether the
    resolved knowledge units land in the expected CS2023 knowledge areas.
    """
    import json as _json
    import os

    from granular.api.services.resolver import QueryResolver
    from granular.evaluation.discover_eval import evaluate_discover_relevance, load_labels

    cfg = _load_config(config_path)

    # ku_id -> knowledge_area from the vocabulary seed.
    vocab = _json.loads(Path(vocabulary_path).read_text(encoding="utf-8"))
    ku_to_area = {u["ku_id"]: u["knowledge_area"] for u in vocab.get("units", [])}

    embedding_model = os.environ.get("OPENAI_EMBEDDING_MODEL", "openai/text-embedding-3-small")
    if "/" not in embedding_model:
        embedding_model = f"openai/{embedding_model}"
    pgvector_dsn = os.environ.get(
        "PGVECTOR_DSN", "postgresql://granular:granular-password@localhost:5432/granular"
    )
    resolution_llm = os.environ.get("RESOLUTION_LLM_MODEL", "openai/gpt-4o")

    resolver = QueryResolver(
        embedding_model_id=embedding_model,
        pgvector_dsn=pgvector_dsn,
        llm_model_id=resolution_llm,
    )

    labels = load_labels(labels_path)
    report = evaluate_discover_relevance(labels, resolver, ku_to_area)

    out_dir = cfg.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "discover_relevance.json").write_text(
        _json.dumps(report.to_dict(), indent=2), encoding="utf-8"
    )

    typer.echo(
        f"\nDiscover relevance — macro P={report.macro_precision:.3f} "
        f"R={report.macro_recall:.3f} F1={report.macro_f1:.3f} "
        f"over {len(report.per_query)} queries"
    )
    for q in report.per_query:
        flag = "" if q.recall == 1.0 and q.precision == 1.0 else "  <-- review"
        typer.echo(
            f"  '{q.query}': P={q.precision:.2f} R={q.recall:.2f} "
            f"resolved={sorted(q.resolved_areas)}{flag}"
        )


@app.command()
def split(
    config_path: Optional[Path] = typer.Option(None, "--config", help="TOML config file"),
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Run identifier"),
) -> None:
    """Create held-out split only (run before granular-infer)."""
    typer.echo("Split creation requires a populated Neo4j graph. Use 'run' for the full flow.")
