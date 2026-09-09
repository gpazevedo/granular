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

    def write_inferred_edge(self, edge: InferredEdge) -> None:
        driver = self._get_driver()
        rel_type = "DEPENDS_ON" if edge.relationship_type.value == "concept_dependency" else "SIMILAR_TO"
        with driver.session() as session:
            session.run(
                f"""
                MATCH (a:Concept {{concept_id: $from_id}})
                MATCH (b:Concept {{concept_id: $to_id}})
                MERGE (a)-[r:{rel_type} {{edge_id: $edge_id}}]->(b)
                SET r.confidence = $confidence,
                    r.model_id = $model_id,
                    r.source_url = $source_url,
                    r.adapter_name = $adapter_name,
                    r.adapter_version = $adapter_version
                """,
                from_id=edge.from_id,
                to_id=edge.to_id,
                edge_id=edge.edge_id,
                confidence=edge.confidence,
                model_id=edge.model_id,
                source_url=edge.provenance.source_url,
                adapter_name=edge.provenance.adapter_name,
                adapter_version=edge.provenance.adapter_version,
            )

    def write_rejected_edge(self, from_id: str, to_id: str, score: float, reason: str, run_id: str) -> None:
        driver = self._get_driver()
        with driver.session() as session:
            session.run(
                """
                CREATE (:RejectedInferredEdge {
                    from_id: $from_id, to_id: $to_id, score: $score,
                    rejection_reason: $reason, run_id: $run_id
                })
                """,
                from_id=from_id, to_id=to_id, score=score, reason=reason, run_id=run_id,
            )

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
