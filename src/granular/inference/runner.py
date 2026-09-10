"""InferenceRunner — orchestrates the concept-graph-inference pipeline."""

from __future__ import annotations

import logging
from collections import defaultdict

from granular.inference.config import InferenceConfig
from granular.inference.dependency import DependencyInferrer
from granular.inference.graph import GraphClient
from granular.inference.ordering import OrderingValidator
from granular.inference.scorer import ConceptNode, DependencyScorer
from granular.inference.signals.prerequisite_prior import PrerequisitePrior
from granular.inference.similarity import SimilarityInferrer
from granular.inference.snapshot import ConceptGraphSnapshot
from granular.inference.summary import InferenceSummary, KACoverageRow

logger = logging.getLogger(__name__)


class InferenceRunner:
    """Top-level orchestrator for concept dependency + similarity inference."""

    def __init__(self, config: InferenceConfig) -> None:
        self._config = config
        self._summary = InferenceSummary()

    def run(self, dry_run: bool = False) -> InferenceSummary:
        cfg = self._config
        graph = GraphClient(cfg.neo4j_uri, cfg.neo4j_user, cfg.neo4j_password)

        # Load concepts and declared prerequisites
        concepts = graph.get_all_concepts()
        declared_prereqs = graph.get_declared_prerequisites()
        self._summary.concepts_processed = len(concepts)
        logger.info(
            "Loaded %d concepts, %d declared prerequisites",
            len(concepts),
            len(declared_prereqs),
        )

        # Build snapshot from existing inferred edges
        snapshot = ConceptGraphSnapshot()
        for f, t in graph.get_existing_inferred_dependencies():
            snapshot.add_edge(f, t)

        # --- Dependency inference ---
        prereq_prior = PrerequisitePrior(declared_prereqs)
        scorer = DependencyScorer(cfg, prereq_prior)
        validator = OrderingValidator(prereq_prior)
        dep_inferrer = DependencyInferrer(cfg, scorer, validator)

        dep_edges, rejections = dep_inferrer.infer(concepts, snapshot, self._summary.run_id)
        self._summary.dependency_edges_inferred = len(dep_edges)
        self._summary.edges_rejected_cycle = sum(
            1 for r in rejections if r.reason == "cycle_prevention"
        )
        self._summary.edges_rejected_ordering = sum(
            1 for r in rejections if r.reason == "prerequisite_ordering_contradiction"
        )

        confidences = [e.confidence for e in dep_edges]

        # --- Similarity inference ---
        concepts_by_ku_raw = graph.get_concepts_by_ku()
        concepts_by_ku: dict[str, list] = {}
        for ku_id, nodes in concepts_by_ku_raw.items():
            # Attach a placeholder confidence (from alignment); use 0.7 default if unknown
            concepts_by_ku[ku_id] = [(n, 0.7) for n in nodes]

        sim_inferrer = SimilarityInferrer(cfg)
        sim_edges, low_conf = sim_inferrer.infer(concepts_by_ku)
        self._summary.similarity_edges_inferred = len(sim_edges)
        self._summary.low_confidence_similarity = low_conf
        confidences.extend(e.confidence for e in sim_edges)

        # --- Write to graph (bulk UNWIND, one transaction per batch) ---
        if not dry_run:
            graph.write_inferred_edges(dep_edges)
            graph.write_inferred_edges(sim_edges)
            graph.write_rejected_edges(
                [
                    {"from_id": r.from_id, "to_id": r.to_id, "score": r.score, "reason": r.reason}
                    for r in rejections
                ],
                self._summary.run_id,
            )

        # --- Knowledge area coverage ---
        self._summary.knowledge_area_coverage = self._build_ka_coverage(
            concepts, dep_edges, sim_edges
        )

        self._summary.compute_confidence_stats(confidences)
        self._summary.finish()
        if not dry_run:
            self._summary.write(cfg.summary_path)

        if self._summary.rejection_rate() > cfg.rejection_threshold_pct:
            logger.error(
                "Rejection rate %.1f%% exceeds threshold %.1f%%",
                self._summary.rejection_rate(),
                cfg.rejection_threshold_pct,
            )

        graph.close()
        return self._summary

    def _build_ka_coverage(
        self,
        concepts: list[ConceptNode],
        dep_edges: list,
        sim_edges: list,
    ) -> list[KACoverageRow]:
        concept_by_id = {c.concept_id: c for c in concepts}
        ka_concepts: dict[str, int] = defaultdict(int)
        ka_dep: dict[str, int] = defaultdict(int)
        ka_sim: dict[str, int] = defaultdict(int)
        ka_conf: dict[str, list[float]] = defaultdict(list)

        for c in concepts:
            if c.knowledge_area:
                ka_concepts[c.knowledge_area] += 1

        for e in dep_edges:
            node = concept_by_id.get(e.from_id)
            if node and node.knowledge_area:
                ka_dep[node.knowledge_area] += 1
                ka_conf[node.knowledge_area].append(e.confidence)

        for e in sim_edges:
            node = concept_by_id.get(e.from_id)
            if node and node.knowledge_area:
                ka_sim[node.knowledge_area] += 1

        all_areas = set(ka_concepts) | set(ka_dep) | set(ka_sim)
        rows: list[KACoverageRow] = []
        for area in sorted(all_areas):
            confs = ka_conf.get(area, [])
            rows.append(
                KACoverageRow(
                    knowledge_area=area,
                    concept_count=ka_concepts.get(area, 0),
                    dependency_edge_count=ka_dep.get(area, 0),
                    similarity_edge_count=ka_sim.get(area, 0),
                    mean_confidence=sum(confs) / len(confs) if confs else 0.0,
                )
            )
        return rows
