"""Neo4jQueryService — all advisory Cypher centralised here (openCypher only)."""

from __future__ import annotations

import logging

from granular.api.services.matcher import CourseMatch

logger = logging.getLogger(__name__)


class Neo4jQueryService:
    """openCypher queries for the advisory layer. No APOC, no GDS."""

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

    def match_courses(self, ku_ids: list[str], level: str) -> list[CourseMatch]:
        driver = self._get_driver()
        matches: list[CourseMatch] = []
        with driver.session() as session:
            result = session.run(
                """
                MATCH (c:Course)<-[:EXTRACTED_FROM]-(concept:Concept)
                      -[:ALIGNED_TO]->(ku:KnowledgeUnit)
                WHERE ku.ku_id IN $ku_ids
                  AND ($level = 'all' OR c.level = $level)
                WITH c,
                     collect(DISTINCT ku.ku_id) AS covered_kus,
                     avg(concept.confidence) AS mean_confidence
                RETURN c.course_id AS course_id,
                       c.course_number AS course_number,
                       c.subject_code AS subject_code,
                       c.title AS title,
                       c.level AS level,
                       c.description AS description,
                       covered_kus,
                       mean_confidence
                ORDER BY mean_confidence DESC, size(covered_kus) DESC
                """,
                ku_ids=ku_ids,
                level=level,
            )
            for row in result:
                desc = row["description"] or ""
                matches.append(
                    CourseMatch(
                        course_id=row["course_id"],
                        course_number=row["course_number"] or "",
                        subject_code=row["subject_code"] or "",
                        title=row["title"] or "",
                        level=row["level"] or "",
                        credits="",
                        description_excerpt=desc[:200],
                        covered_ku_ids=list(row["covered_kus"]),
                        relevance_score=float(row["mean_confidence"] or 0.0),
                    )
                )
        return matches

    def declared_prereqs_between(self, course_ids: list[str]) -> set[tuple[str, str]]:
        driver = self._get_driver()
        pairs: set[tuple[str, str]] = set()
        with driver.session() as session:
            result = session.run(
                """
                MATCH (a:Course)-[:PREREQUISITE]->(b:Course)
                WHERE a.course_id IN $ids AND b.course_id IN $ids
                RETURN a.course_id AS course, b.course_id AS prereq
                """,
                ids=course_ids,
            )
            for row in result:
                pairs.add((row["course"], row["prereq"]))
        return pairs

    def thin_coverage_units(self, ku_ids: list[str], min_courses: int) -> list[str]:
        driver = self._get_driver()
        thin: list[str] = []
        with driver.session() as session:
            result = session.run(
                """
                MATCH (ku:KnowledgeUnit)
                WHERE ku.ku_id IN $ku_ids
                OPTIONAL MATCH (ku)<-[:ALIGNED_TO]-(concept:Concept)
                              -[:EXTRACTED_FROM]->(c:Course)
                WITH ku, count(DISTINCT c) AS course_count
                WHERE course_count < $min_courses
                RETURN ku.ku_id AS ku_id
                """,
                ku_ids=ku_ids,
                min_courses=min_courses,
            )
            for row in result:
                thin.append(row["ku_id"])
        return thin

    def ku_labels(self, ku_ids: list[str]) -> dict[str, tuple[str, str]]:
        """Return ku_id -> (label, knowledge_area)."""
        driver = self._get_driver()
        labels: dict[str, tuple[str, str]] = {}
        with driver.session() as session:
            result = session.run(
                """
                MATCH (ku:KnowledgeUnit) WHERE ku.ku_id IN $ku_ids
                RETURN ku.ku_id AS ku_id, ku.label AS label, ku.knowledge_area AS area
                """,
                ku_ids=ku_ids,
            )
            for row in result:
                labels[row["ku_id"]] = (row["label"] or "", row["area"] or "")
        return labels

    def close(self) -> None:
        if self._driver:
            self._driver.close()
