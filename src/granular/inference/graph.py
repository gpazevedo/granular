"""GraphClient — Neo4j read/write wrapper for the inference pipeline.

All queries use openCypher only. No APOC, no GDS. Swappable to any
openCypher-compatible store by changing the driver and connection config.
"""

from __future__ import annotations

import logging

from granular.inference.scorer import ConceptNode
from granular.schema import InferredEdge

logger = logging.getLogger(__name__)


class GraphClient:
    """openCypher wrapper over the neo4j driver for inference reads and writes."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            try:
                from neo4j import GraphDatabase
                self._driver = GraphDatabase.driver(
                    self._uri, auth=(self._user, self._password)
                )
            except ImportError:
                raise ImportError("neo4j driver required: pip install neo4j")
        return self._driver

    def get_all_concepts(self) -> list[ConceptNode]:
        driver = self._get_driver()
        nodes: list[ConceptNode] = []
        with driver.session() as session:
            result = session.run(
                """
                MATCH (c:Concept)-[:EXTRACTED_FROM]->(course:Course)
                OPTIONAL MATCH (c)-[:ALIGNED_TO]->(k:KnowledgeUnit)
                RETURN c.concept_id AS concept_id,
                       c.label AS label,
                       course.course_id AS source_course_id,
                       course.course_number AS course_number,
                       coalesce(k.knowledge_area, '') AS knowledge_area
                """
            )
            for row in result:
                nodes.append(
                    ConceptNode(
                        concept_id=row["concept_id"],
                        label=row["label"],
                        source_course_id=row["source_course_id"],
                        course_number=row["course_number"] or "",
                        knowledge_area=row["knowledge_area"],
                    )
                )
        return nodes

    def get_declared_prerequisites(self) -> set[tuple[str, str]]:
        driver = self._get_driver()
        prereqs: set[tuple[str, str]] = set()
        with driver.session() as session:
            result = session.run(
                """
                MATCH (a:Course)-[r:PREREQUISITE]->(b:Course)
                RETURN a.course_id AS course, b.course_id AS prereq
                """
            )
            for row in result:
                prereqs.add((row["course"], row["prereq"]))
        return prereqs

    @staticmethod
    def _rel_type(edge: InferredEdge) -> str:
        return (
            "DEPENDS_ON"
            if edge.relationship_type.value == "concept_dependency"
            else "SIMILAR_TO"
        )

    @staticmethod
    def _edge_row(edge: InferredEdge) -> dict:
        return {
            "from_id": edge.from_id,
            "to_id": edge.to_id,
            "edge_id": edge.edge_id,
            "confidence": edge.confidence,
            "model_id": edge.model_id,
            "source_url": edge.provenance.source_url,
            "adapter_name": edge.provenance.adapter_name,
            "adapter_version": edge.provenance.adapter_version,
        }

    def write_inferred_edge(self, edge: InferredEdge) -> None:
        """Write a single inferred edge. Prefer write_inferred_edges for bulk."""
        self.write_inferred_edges([edge])

    def write_inferred_edges(self, edges: list[InferredEdge], batch_size: int = 5000) -> int:
        """Bulk-write inferred edges using UNWIND, one transaction per batch.

        Replaces the previous one-session-per-edge approach, which made large
        inference runs take tens of minutes. Edges are grouped by relationship
        type (the type is fixed in the query text) and written in chunks.

        Returns the number of edges written.
        """
        if not edges:
            return 0

        by_type: dict[str, list[dict]] = {}
        for edge in edges:
            by_type.setdefault(self._rel_type(edge), []).append(self._edge_row(edge))

        driver = self._get_driver()
        written = 0
        with driver.session() as session:
            for rel_type, rows in by_type.items():
                query = f"""
                    UNWIND $rows AS row
                    MATCH (a:Concept {{concept_id: row.from_id}})
                    MATCH (b:Concept {{concept_id: row.to_id}})
                    MERGE (a)-[r:{rel_type} {{edge_id: row.edge_id}}]->(b)
                    SET r.confidence = row.confidence,
                        r.model_id = row.model_id,
                        r.source_url = row.source_url,
                        r.adapter_name = row.adapter_name,
                        r.adapter_version = row.adapter_version
                """
                for start in range(0, len(rows), batch_size):
                    chunk = rows[start : start + batch_size]
                    session.execute_write(lambda tx, c=chunk: tx.run(query, rows=c).consume())
                    written += len(chunk)
        return written

    def write_rejected_edge(self, from_id: str, to_id: str, score: float, reason: str, run_id: str) -> None:
        """Write a single rejected-edge record. Prefer write_rejected_edges for bulk."""
        self.write_rejected_edges(
            [{"from_id": from_id, "to_id": to_id, "score": score, "reason": reason}],
            run_id,
        )

    def write_rejected_edges(self, rows: list[dict], run_id: str, batch_size: int = 5000) -> int:
        """Bulk-write RejectedInferredEdge records using UNWIND.

        Each row is {from_id, to_id, score, reason}.
        """
        if not rows:
            return 0
        payload = [
            {
                "from_id": r["from_id"],
                "to_id": r["to_id"],
                "score": r["score"],
                "reason": r["reason"],
                "run_id": run_id,
            }
            for r in rows
        ]
        driver = self._get_driver()
        query = """
            UNWIND $rows AS row
            CREATE (:RejectedInferredEdge {
                from_id: row.from_id, to_id: row.to_id, score: row.score,
                rejection_reason: row.reason, run_id: row.run_id
            })
        """
        written = 0
        with driver.session() as session:
            for start in range(0, len(payload), batch_size):
                chunk = payload[start : start + batch_size]
                session.execute_write(lambda tx, c=chunk: tx.run(query, rows=c).consume())
                written += len(chunk)
        return written

    def get_existing_inferred_dependencies(self) -> list[tuple[str, str]]:
        driver = self._get_driver()
        edges: list[tuple[str, str]] = []
        with driver.session() as session:
            result = session.run(
                "MATCH (a:Concept)-[:DEPENDS_ON]->(b:Concept) RETURN a.concept_id AS f, b.concept_id AS t"
            )
            for row in result:
                edges.append((row["f"], row["t"]))
        return edges

    def get_concepts_by_ku(self) -> dict[str, list[ConceptNode]]:
        """Return concepts grouped by knowledge_unit_id (aligned only)."""
        driver = self._get_driver()
        by_ku: dict[str, list[ConceptNode]] = {}
        with driver.session() as session:
            result = session.run(
                """
                MATCH (c:Concept)-[:ALIGNED_TO]->(k:KnowledgeUnit)
                MATCH (c)-[:EXTRACTED_FROM]->(course:Course)
                RETURN k.ku_id AS ku_id,
                       c.concept_id AS concept_id,
                       c.label AS label,
                       c.confidence AS confidence,
                       course.course_id AS source_course_id,
                       course.course_number AS course_number,
                       k.knowledge_area AS knowledge_area
                """
            )
            for row in result:
                node = ConceptNode(
                    concept_id=row["concept_id"],
                    label=row["label"],
                    source_course_id=row["source_course_id"],
                    course_number=row["course_number"] or "",
                    knowledge_area=row["knowledge_area"] or "",
                )
                by_ku.setdefault(row["ku_id"], []).append(node)
        return by_ku

    def close(self) -> None:
        if self._driver:
            self._driver.close()
