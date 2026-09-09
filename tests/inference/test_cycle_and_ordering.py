"""Tests for cycle resolution and ordering validation."""

from __future__ import annotations

from datetime import datetime, timezone

from granular.inference.config import InferenceConfig
from granular.inference.cycle import resolve_cycles
from granular.inference.ordering import OrderingValidator, ValidationResult
from granular.inference.scorer import ConceptNode
from granular.inference.signals.prerequisite_prior import PrerequisitePrior
from granular.inference.snapshot import ConceptGraphSnapshot
from granular.schema import InferredEdge, InferredEdgeType, ProvenanceRecord


def make_edge(from_id: str, to_id: str, confidence: float = 0.5) -> InferredEdge:
    return InferredEdge(
        provenance=ProvenanceRecord(
            source_url="https://granular.local/inferred/test",
            retrieved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            adapter_name="test",
            adapter_version="1.0.0",
            source_revision=None,
        ),
        model_id="test-model",
        confidence=confidence,
        edge_id=f"e-{from_id}-{to_id}",
        from_id=from_id,
        to_id=to_id,
        relationship_type=InferredEdgeType.CONCEPT_DEPENDENCY,
    )


class TestCycleResolver:
    def test_no_cycle_all_survive(self):
        snap = ConceptGraphSnapshot()
        candidates = [
            (make_edge("A", "B", 0.8), 0.8),
            (make_edge("B", "C", 0.7), 0.7),
        ]
        surviving, rejected = resolve_cycles(snap, candidates)
        assert len(surviving) == 2
        assert len(rejected) == 0

    def test_cycle_removes_lowest_confidence(self):
        snap = ConceptGraphSnapshot()
        candidates = [
            (make_edge("A", "B", 0.9), 0.9),
            (make_edge("B", "C", 0.8), 0.8),
            (make_edge("C", "A", 0.3), 0.3),  # lowest — should be removed
        ]
        surviving, rejected = resolve_cycles(snap, candidates)
        assert len(rejected) == 1
        assert rejected[0].reason == "cycle_prevention"
        # The removed edge should be the lowest-confidence one
        assert (rejected[0].from_id, rejected[0].to_id) == ("C", "A")
        assert not snap.has_cycle()


class TestOrderingValidator:
    def _node(self, cid: str, course: str) -> ConceptNode:
        return ConceptNode(
            concept_id=cid,
            label="x",
            source_course_id=course,
            course_number=course.split("-")[1],
            knowledge_area="AL",
        )

    def test_ok_when_no_contradiction(self):
        prior = PrerequisitePrior({("CS-25100", "CS-18000")})
        validator = OrderingValidator(prior)
        # A (25100) depends on B (18000); declared says 25100 requires 18000 → OK
        result = validator.check(
            self._node("cA", "CS-25100"), self._node("cB", "CS-18000")
        )
        assert result == ValidationResult.OK

    def test_contradiction_when_reversed(self):
        # Declared: 25100 requires 18000. So course 25100 comes AFTER 18000.
        # Inferred: concept in 18000 depends on concept in 25100 → contradiction.
        prior = PrerequisitePrior({("CS-25100", "CS-18000")})
        validator = OrderingValidator(prior)
        result = validator.check(
            self._node("cB", "CS-18000"), self._node("cA", "CS-25100")
        )
        assert result == ValidationResult.CONTRADICTION
