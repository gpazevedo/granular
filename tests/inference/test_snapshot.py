"""Tests for ConceptGraphSnapshot cycle detection."""

from __future__ import annotations

from granular.inference.snapshot import ConceptGraphSnapshot


class TestConceptGraphSnapshot:
    def test_no_cycle_empty(self):
        snap = ConceptGraphSnapshot()
        assert not snap.has_cycle()

    def test_no_cycle_linear(self):
        snap = ConceptGraphSnapshot()
        snap.add_edge("A", "B")
        snap.add_edge("B", "C")
        assert not snap.has_cycle()

    def test_simple_cycle(self):
        snap = ConceptGraphSnapshot()
        snap.add_edge("A", "B")
        snap.add_edge("B", "A")
        assert snap.has_cycle()

    def test_three_node_cycle(self):
        snap = ConceptGraphSnapshot()
        snap.add_edge("A", "B")
        snap.add_edge("B", "C")
        snap.add_edge("C", "A")
        assert snap.has_cycle()

    def test_self_loop(self):
        snap = ConceptGraphSnapshot()
        snap.add_edge("A", "A")
        assert snap.has_cycle()

    def test_remove_edge_breaks_cycle(self):
        snap = ConceptGraphSnapshot()
        snap.add_edge("A", "B")
        snap.add_edge("B", "A")
        assert snap.has_cycle()
        snap.remove_edge("B", "A")
        assert not snap.has_cycle()

    def test_find_cycle_edges(self):
        snap = ConceptGraphSnapshot()
        snap.add_edge("A", "B")
        snap.add_edge("B", "C")
        snap.add_edge("C", "A")
        cycle = snap.find_cycle_edges()
        assert len(cycle) > 0

    def test_edge_count(self):
        snap = ConceptGraphSnapshot()
        snap.add_edge("A", "B")
        snap.add_edge("A", "C")
        assert snap.edge_count() == 2
