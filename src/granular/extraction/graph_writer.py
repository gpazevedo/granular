"""GraphWriter — writes Concept nodes and alignment edges to Neo4j.

All queries use openCypher only. No APOC, no GDS.
"""

from __future__ import annotations

import logging

from granular.schema import AlignmentStatus, Concept, KnowledgeUnit

logger = logging.getLogger(__name__)


class GraphWriter:
    """Writes extraction results to Neo4j using openCypher."""

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

    def write_knowledge_unit(self, ku: KnowledgeUnit) -> None:
        driver = self._get_driver()
        with driver.session() as session:
            session.run(
                """
                MERGE (k:KnowledgeUnit {ku_id: $ku_id})
                SET k.label = $label,
                    k.knowledge_area = $knowledge_area,
                    k.tier = $tier,
                    k.source = $source
                """,
                ku_id=ku.ku_id,
                label=ku.label,
                knowledge_area=ku.knowledge_area,
                tier=ku.tier.value,
                source=ku.source,
            )

    def write_course(self, course) -> None:
        """Write (or enrich) a Course node with the properties inference needs.

        In particular `course_number` is required by the inference pipeline's
        course-level signal; a bare `course_id`-only node is not sufficient.
        """
        driver = self._get_driver()
        with driver.session() as session:
            session.run(
                """
                MERGE (course:Course {course_id: $course_id})
                SET course.course_number = $course_number,
                    course.subject_code = $subject_code,
                    course.title = $title,
                    course.level = $level,
                    course.description = $description
                """,
                course_id=course.course_id,
                course_number=str(course.course_number),
                subject_code=course.subject_code,
                title=course.title,
                level=course.level.value,
                description=course.description or "",
            )

    def write_prerequisite_edges(
        self,
        course_id: str,
        prereq_course_ids: list[str],
        verbatim_by_prereq: dict[str, str] | None = None,
    ) -> None:
        """Write declared PREREQUISITE edges: (course)-[:PREREQUISITE]->(prereq).

        The prerequisite target courses are MERGEd as Course nodes so the edge
        exists even if that course has no extracted concepts of its own.
        ``verbatim_by_prereq`` optionally supplies the catalogue's verbatim
        wording per prerequisite course id, stored on the edge for the
        readiness advisory query.
        """
        if not prereq_course_ids:
            return
        verbatim_by_prereq = verbatim_by_prereq or {}
        driver = self._get_driver()
        with driver.session() as session:
            for prereq_id in prereq_course_ids:
                session.run(
                    """
                    MERGE (a:Course {course_id: $course_id})
                    MERGE (b:Course {course_id: $prereq_id})
                    MERGE (a)-[r:PREREQUISITE]->(b)
                    SET r.verbatim_text = $verbatim
                    """,
                    course_id=course_id,
                    prereq_id=prereq_id,
                    verbatim=verbatim_by_prereq.get(prereq_id, ""),
                )

    def write_concept(self, concept: Concept) -> None:
        """Write a Concept node and, if aligned, an ALIGNED_TO edge."""
        driver = self._get_driver()
        with driver.session() as session:
            session.run(
                """
                MERGE (c:Concept {concept_id: $concept_id})
                SET c.label = $label,
                    c.source_course_id = $source_course_id,
                    c.confidence = $confidence,
                    c.model_id = $model_id,
                    c.alignment_status = $alignment_status
                MERGE (course:Course {course_id: $source_course_id})
                MERGE (c)-[:EXTRACTED_FROM]->(course)
                """,
                concept_id=concept.concept_id,
                label=concept.label,
                source_course_id=concept.source_course_id,
                confidence=concept.confidence,
                model_id=concept.model_id,
                alignment_status=concept.alignment_status.value,
            )

            if (
                concept.alignment_status == AlignmentStatus.ALIGNED
                and concept.knowledge_unit_id
            ):
                session.run(
                    """
                    MATCH (c:Concept {concept_id: $concept_id})
                    MATCH (k:KnowledgeUnit {ku_id: $ku_id})
                    MERGE (c)-[r:ALIGNED_TO]->(k)
                    SET r.confidence = $confidence,
                        r.model_id = $model_id
                    """,
                    concept_id=concept.concept_id,
                    ku_id=concept.knowledge_unit_id,
                    confidence=concept.confidence,
                    model_id=concept.model_id,
                )

    def concept_exists(self, course_id: str, label: str) -> bool:
        driver = self._get_driver()
        with driver.session() as session:
            result = session.run(
                """
                MATCH (c:Concept {source_course_id: $course_id, label: $label})
                RETURN count(c) AS n
                """,
                course_id=course_id,
                label=label,
            )
            record = result.single()
            return record["n"] > 0 if record else False

    def close(self) -> None:
        if self._driver:
            self._driver.close()
