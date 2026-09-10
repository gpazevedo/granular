"""DiscoverService — orchestrates interest-driven discovery (pure orchestration).

Kept separate from FastAPI routing so it can be tested with fakes for the
resolver and graph query service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from granular.api.config import APIConfig
from granular.api.guards.language_guard import EntitlementLanguageGuard
from granular.api.models.responses import (
    CombinationResult,
    CourseResult,
    DiscoverResponse,
    KULabel,
    PrereqNote as PrereqNoteModel,
    RedundancyNote as RedundancyNoteModel,
    ThinCoverageNote,
)
from granular.api.services.combinator import build_combinations
from granular.api.services.matcher import (
    CourseMatch,
    composite_score,
    coverage_breadth,
    rank_courses,
)
from granular.api.services.resolver import ResolutionResult


class ResolverProtocol(Protocol):
    def resolve(self, query: str) -> ResolutionResult: ...


class GraphProtocol(Protocol):
    def match_courses(
        self, ku_ids: list[str], level: str, min_confidence: float = 0.0
    ) -> list[CourseMatch]: ...
    def declared_prereqs_between(self, course_ids: list[str]) -> set[tuple[str, str]]: ...
    def thin_coverage_units(self, ku_ids: list[str], min_courses: int) -> list[str]: ...
    def ku_labels(self, ku_ids: list[str]) -> dict[str, tuple[str, str]]: ...


class DiscoverService:
    def __init__(
        self,
        resolver: ResolverProtocol,
        graph: GraphProtocol,
        config: APIConfig,
    ) -> None:
        self._resolver = resolver
        self._graph = graph
        self._config = config
        self._guard = EntitlementLanguageGuard(config.entitlement_patterns)

    def discover(self, query: str, level: str) -> DiscoverResponse:
        resolution = self._resolver.resolve(query)

        if not resolution.resolved:
            return DiscoverResponse(
                resolved_kus=[],
                courses=[],
                combinations=[],
                thin_coverage=[],
                status="no_concepts_resolved",
                status_message=(
                    "Could not resolve your interest to any known concepts. "
                    "Try rephrasing with more specific technical terms."
                ),
            )

        ku_ids = resolution.ku_ids
        ku_label_map = self._graph.ku_labels(ku_ids)
        resolved_kus = [
            KULabel(ku_id=k, label=ku_label_map.get(k, ("", ""))[0], knowledge_area=ku_label_map.get(k, ("", ""))[1])
            for k in ku_ids
        ]

        matches = self._graph.match_courses(ku_ids, level, self._config.match_min_confidence)

        if not matches:
            return DiscoverResponse(
                resolved_kus=resolved_kus,
                courses=[],
                combinations=[],
                thin_coverage=[],
                status="no_courses_found",
                status_message=(
                    "No courses with concepts aligned to your interest were found. "
                    "Try related terms."
                ),
            )

        ranked = rank_courses(matches, len(ku_ids))

        # Thin coverage
        thin_ids = self._graph.thin_coverage_units(ku_ids, self._config.min_coverage_courses)
        thin_notes = [
            ThinCoverageNote(ku_id=k, label=ku_label_map.get(k, ("", ""))[0])
            for k in thin_ids
        ]

        # Combinations
        course_ids = [m.course_id for m in ranked]
        declared = self._graph.declared_prereqs_between(course_ids)
        combos = build_combinations(
            ranked,
            total_resolved_kus=len(ku_ids),
            declared_prereqs=declared,
            max_size=self._config.max_combination_size,
            max_results=self._config.max_combinations,
        )

        # Build response models
        course_results = [self._to_course_result(m, len(ku_ids)) for m in ranked]
        combination_results = [self._to_combination_result(c) for c in combos]

        response = DiscoverResponse(
            resolved_kus=resolved_kus,
            courses=course_results,
            combinations=combination_results,
            thin_coverage=thin_notes,
            status="ok",
        )

        self._guard_response(response)
        return response

    def _to_course_result(self, m: CourseMatch, total_kus: int) -> CourseResult:
        return CourseResult(
            course_id=m.course_id,
            course_number=m.course_number,
            subject_code=m.subject_code,
            title=m.title,
            level=m.level,
            credits=m.credits,
            description_excerpt=m.description_excerpt,
            # relevance_score is the composite (coverage-weighted) that drives
            # ranking; confidence is the raw mean alignment confidence (REQ-AQ-03).
            relevance_score=round(
                composite_score(len(m.covered_ku_ids), total_kus, m.relevance_score), 3
            ),
            coverage_breadth=coverage_breadth(len(m.covered_ku_ids), total_kus),
            covered_ku_ids=m.covered_ku_ids,
            confidence=round(m.relevance_score, 3),
        )

    def _to_combination_result(self, c) -> CombinationResult:
        return CombinationResult(
            course_numbers=[cm.course_number for cm in c.courses],
            course_titles=[cm.title for cm in c.courses],
            combined_coverage_breadth=c.combined_coverage_breadth,
            combined_ku_ids=c.combined_ku_ids,
            redundancies=[
                RedundancyNoteModel(
                    course_a_number=r.course_a_number,
                    course_b_number=r.course_b_number,
                    overlapping_ku_labels=r.overlapping_ku_ids,
                )
                for r in c.redundancies
            ],
            prerequisite_order=[
                PrereqNoteModel(
                    take_first=p.take_first,
                    then=p.then,
                    declared=p.declared,
                    message=p.message or None,
                )
                for p in c.prerequisite_order
            ],
            combined_relevance=round(c.combined_relevance, 3),
        )

    def _guard_response(self, response: DiscoverResponse) -> None:
        """Apply the entitlement-language guard to all text fields."""
        for course in response.courses:
            self._guard.assert_clean(course.title)
            self._guard.assert_clean(course.description_excerpt)
            self._guard.assert_clean(course.caveat)
        for combo in response.combinations:
            for title in combo.course_titles:
                self._guard.assert_clean(title)
            self._guard.assert_clean(combo.caveat)
