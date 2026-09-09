"""CycleResolver — guarantees the concept dependency graph remains a DAG."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from granular.inference.snapshot import ConceptGraphSnapshot
from granular.schema import InferredEdge

logger = logging.getLogger(__name__)


@dataclass
class RejectedEdge:
    from_id: str
    to_id: str
    score: float
    reason: str


def resolve_cycles(
    snapshot: ConceptGraphSnapshot,
    candidates: list[tuple[InferredEdge, float]],
) -> tuple[list[InferredEdge], list[RejectedEdge]]:
    """Add candidate edges to the snapshot and remove the lowest-confidence
    edge in any cycle until the graph is acyclic.

    Returns (surviving_edges, rejected_edges). Never raises.
    """
    # Sort candidates by score descending so lower-score edges are removed first
    score_by_pair: dict[tuple[str, str], float] = {}
    edge_by_pair: dict[tuple[str, str], InferredEdge] = {}
    for edge, score in candidates:
        pair = (edge.from_id, edge.to_id)
        score_by_pair[pair] = score
        edge_by_pair[pair] = edge
        snapshot.add_edge(edge.from_id, edge.to_id)

    rejected: list[RejectedEdge] = []

    while snapshot.has_cycle():
        cycle_edges = snapshot.find_cycle_edges()
        if not cycle_edges:
            break
        # Remove the lowest-scoring edge in the cycle
        lowest = min(
            cycle_edges,
            key=lambda pair: score_by_pair.get(pair, 0.0),
        )
        snapshot.remove_edge(lowest[0], lowest[1])
        rejected.append(
            RejectedEdge(
                from_id=lowest[0],
                to_id=lowest[1],
                score=score_by_pair.get(lowest, 0.0),
                reason="cycle_prevention",
            )
        )
        edge_by_pair.pop(lowest, None)
        logger.debug("Removed edge %s->%s for cycle prevention", lowest[0], lowest[1])

    surviving = list(edge_by_pair.values())
    return surviving, rejected
