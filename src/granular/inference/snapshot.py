"""ConceptGraphSnapshot — in-memory DAG for cycle detection."""

from __future__ import annotations

from collections import defaultdict


class ConceptGraphSnapshot:
    """In-memory directed graph of concept_dependency edges.

    Used exclusively for cycle detection. Not a full graph replica.
    """

    def __init__(self) -> None:
        self._adj: dict[str, set[str]] = defaultdict(set)

    def add_edge(self, from_id: str, to_id: str) -> None:
        self._adj[from_id].add(to_id)

    def remove_edge(self, from_id: str, to_id: str) -> None:
        self._adj[from_id].discard(to_id)

    def has_cycle(self) -> bool:
        """Detect any cycle via DFS with colour marking."""
        WHITE, GREY, BLACK = 0, 1, 2
        colour: dict[str, int] = defaultdict(int)

        def visit(node: str) -> bool:
            colour[node] = GREY
            for neighbour in self._adj.get(node, set()):
                if colour[neighbour] == GREY:
                    return True
                if colour[neighbour] == WHITE and visit(neighbour):
                    return True
            colour[node] = BLACK
            return False

        nodes = set(self._adj.keys())
        for targets in self._adj.values():
            nodes.update(targets)

        for node in nodes:
            if colour[node] == WHITE:
                if visit(node):
                    return True
        return False

    def find_cycle_edges(self) -> list[tuple[str, str]]:
        """Return the edges forming one detected cycle, or [] if acyclic."""
        WHITE, GREY, BLACK = 0, 1, 2
        colour: dict[str, int] = defaultdict(int)
        parent: dict[str, str] = {}
        cycle: list[tuple[str, str]] = []

        def visit(node: str) -> bool:
            colour[node] = GREY
            for neighbour in self._adj.get(node, set()):
                if colour[neighbour] == GREY:
                    # Found a back edge — reconstruct the cycle
                    cur = node
                    cycle.append((node, neighbour))
                    while cur != neighbour and cur in parent:
                        cycle.append((parent[cur], cur))
                        cur = parent[cur]
                    return True
                if colour[neighbour] == WHITE:
                    parent[neighbour] = node
                    if visit(neighbour):
                        return True
            colour[node] = BLACK
            return False

        nodes = set(self._adj.keys())
        for targets in self._adj.values():
            nodes.update(targets)

        for node in nodes:
            if colour[node] == WHITE:
                if visit(node):
                    return cycle
        return []

    def edge_count(self) -> int:
        return sum(len(t) for t in self._adj.values())
