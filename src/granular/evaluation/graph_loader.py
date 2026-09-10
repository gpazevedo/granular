"""Neo4j-backed loader for the evaluation harness InferredGraph.

Uses openCypher only. Reads the graph; never writes to the live graph.
"""

from __future__ import annotations

import logging

from granular.evaluation.metric import InferredDepEdge, InferredGraph

logger = logging.getLogger(__name__)


class Neo4jGraphLoader:
    """Loads the inferred concept graph and declared prerequisites from Neo4j."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))
        return self._driver

    def __call__(self) -> tuple[InferredGraph, set[tuple[str, str]]]:
        driver = self._get_driver()
        concept_to_course: dict[str, str] = {}
        concept_to_area: dict[str, str] = {}
        edges: list[InferredDepEdge] = []
        declared: set[tuple[str, str]] = set()

        with driver.session() as session:
            # Concepts and their course + KA
            result = session.run(
                """
                MATCH (c:Concept)-[:EXTRACTED_FROM]->(course:Course)
                OPTIONAL MATCH (c)-[:ALIGNED_TO]->(k:KnowledgeUnit)
                RETURN c.concept_id AS cid, course.course_id AS course,
                       coalesce(k.knowledge_area, '') AS area
                """
            )
            for row in result:
                concept_to_course[row["cid"]] = row["course"]
                concept_to_area[row["cid"]] = row["area"]

            # Inferred dependency edges
            result = session.run(
                """
                MATCH (a:Concept)-[r:DEPENDS_ON]->(b:Concept)
                RETURN a.concept_id AS f, b.concept_id AS t, r.confidence AS conf
                """
            )
            for row in result:
                edges.append(
                    InferredDepEdge(
                        from_concept=row["f"],
                        to_concept=row["t"],
                        confidence=float(row["conf"]),
                    )
                )

            # Declared prerequisites
            result = session.run(
                """
                MATCH (a:Course)-[:PREREQUISITE]->(b:Course)
                RETURN a.course_id AS course, b.course_id AS prereq
                """
            )
            for row in result:
                declared.add((row["course"], row["prereq"]))

        graph = InferredGraph(
            concept_to_course=concept_to_course,
            concept_to_area=concept_to_area,
            edges=edges,
        )
        return graph, declared

    def load_concepts_for_ablation(self) -> list:
        """Load all concepts as inference ConceptNode records (for real ablation)."""
        from granular.inference.scorer import ConceptNode

        driver = self._get_driver()
        out: list[ConceptNode] = []
        with driver.session() as session:
            result = session.run(
                """
                MATCH (c:Concept)-[:EXTRACTED_FROM]->(course:Course)
                OPTIONAL MATCH (c)-[:ALIGNED_TO]->(k:KnowledgeUnit)
                RETURN c.concept_id AS cid, c.label AS label,
                       course.course_id AS course, course.course_number AS cnum,
                       coalesce(k.knowledge_area, '') AS area
                """
            )
            for row in result:
                out.append(
                    ConceptNode(
                        concept_id=row["cid"],
                        label=row["label"] or "",
                        source_course_id=row["course"] or "",
                        course_number=row["cnum"] or "",
                        knowledge_area=row["area"] or "",
                    )
                )
        return out

    def load_aligned_concepts(self) -> list:
        """Load all ALIGNED concepts with their KU, for alignment-precision eval."""
        from granular.evaluation.alignment_eval import AlignedConcept

        driver = self._get_driver()
        out: list[AlignedConcept] = []
        with driver.session() as session:
            result = session.run(
                """
                MATCH (c:Concept)-[:EXTRACTED_FROM]->(course:Course)
                MATCH (c)-[:ALIGNED_TO]->(k:KnowledgeUnit)
                RETURN c.concept_id AS cid, c.label AS clabel, course.course_id AS course,
                       k.ku_id AS ku_id, k.label AS ku_label,
                       k.knowledge_area AS area, c.confidence AS conf
                """
            )
            for row in result:
                out.append(
                    AlignedConcept(
                        concept_id=row["cid"],
                        concept_label=row["clabel"] or "",
                        course_id=row["course"] or "",
                        ku_id=row["ku_id"] or "",
                        ku_label=row["ku_label"] or "",
                        knowledge_area=row["area"] or "",
                        confidence=float(row["conf"] or 0.0),
                    )
                )
        return out

    def close(self) -> None:
        if self._driver:
            self._driver.close()
