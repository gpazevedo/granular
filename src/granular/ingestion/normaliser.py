"""Normaliser — converts RawCourse / RawProgramme into canonical schema records.

Pure function: no network, no I/O. All errors surface as NormaliserError.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Optional

from granular.ingestion.adapters.acalog.course_parser import RawCourse
from granular.ingestion.adapters.acalog.programme_parser import RawProgramme
from granular.ingestion.adapters.acalog.prereq_parser import parse_prerequisite
from granular.ingestion.config import IngestConfig
from granular.schema import (
    Authority,
    Course,
    CreditRange,
    DeclaredEdge,
    DeclaredEdgeType,
    Programme,
    ProgrammeLevel,
    ProvenanceRecord,
    RequirementRule,
    RuleType,
    SchemaValidationError,
)

logger = logging.getLogger(__name__)

_CREDIT_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s+to\s+(\d+(?:\.\d+)?)", re.IGNORECASE)
_CREDIT_FIXED_RE = re.compile(r"(\d+(?:\.\d+)?)")
_COURSE_ID_RE = re.compile(r"\b([A-Z]{2,5})\s+(\d{5}[A-Z]?)\b")


class NormaliserError(Exception):
    """Raised when normalisation fails for a single record."""

    def __init__(self, source_url: str, reason: str, cause: Optional[Exception] = None) -> None:
        self.source_url = source_url
        self.reason = reason
        self.cause = cause
        super().__init__(f"[{source_url}] {reason}")


def _parse_credits(raw: str) -> float | CreditRange:
    if not raw or "variable" in raw.lower():
        logger.warning("Variable/unknown credits: %r; defaulting to CreditRange(0,0)", raw)
        return CreditRange(0.0, 0.0)
    range_m = _CREDIT_RANGE_RE.search(raw)
    if range_m:
        return CreditRange(float(range_m.group(1)), float(range_m.group(2)))
    fixed_m = _CREDIT_FIXED_RE.search(raw)
    if fixed_m:
        return float(fixed_m.group(1))
    logger.warning("Could not parse credits from %r; defaulting to 3.0", raw)
    return 3.0


def _parse_level(raw: str) -> ProgrammeLevel:
    if raw.strip().lower() == "graduate":
        return ProgrammeLevel.GRADUATE
    return ProgrammeLevel.UNDERGRADUATE


def _make_course_id(subject: str, number: str) -> str:
    return f"{subject}-{number}"


def normalise_course(
    raw: RawCourse,
    config: IngestConfig,
) -> tuple[Course, list[DeclaredEdge]]:
    """Convert a RawCourse to a Course + list of DeclaredEdges.

    Returns (course, edges).
    Raises NormaliserError on schema validation failure.
    """
    try:
        provenance = ProvenanceRecord(
            source_url=raw.source_url,
            retrieved_at=raw.retrieved_at,
            adapter_name=config.adapter_name,
            adapter_version=config.adapter_version,
            source_revision=raw.source_revision,
        )

        credits = _parse_credits(raw.credits_raw)
        level = _parse_level(raw.level_raw)
        course_id = _make_course_id(raw.subject_code, raw.course_number)

        # Parse prerequisites
        prereq_rules = []
        edges: list[DeclaredEdge] = []
        if raw.prereqs_raw:
            rule = parse_prerequisite(f"prereq-{course_id}", raw.prereqs_raw)
            prereq_rules.append(rule)
            if rule.machine_checkable and rule.structured is not None:
                # Extract all SingleCourse nodes from the predicate tree
                course_refs = _collect_course_ids(rule.structured)
                for ref_id in course_refs:
                    edges.append(
                        DeclaredEdge(
                            provenance=provenance,
                            edge_id=f"prereq-{course_id}-{ref_id}-{uuid.uuid4().hex[:8]}",
                            from_id=course_id,
                            to_id=ref_id,
                            relationship_type=DeclaredEdgeType.PREREQUISITE,
                        )
                    )

        # Parse cross-listings
        cross_listing_ids: list[str] = []
        for raw_cross in raw.cross_list_raw:
            m = _COURSE_ID_RE.search(raw_cross)
            if m:
                xid = _make_course_id(m.group(1), m.group(2))
                cross_listing_ids.append(xid)
                edges.append(
                    DeclaredEdge(
                        provenance=provenance,
                        edge_id=f"crosslist-{course_id}-{xid}",
                        from_id=course_id,
                        to_id=xid,
                        relationship_type=DeclaredEdgeType.CROSS_LISTING,
                    )
                )

        course = Course(
            provenance=provenance,
            course_id=course_id,
            authority=Authority.DERIVED,
            subject_code=raw.subject_code,
            course_number=raw.course_number,
            title=raw.title,
            description=raw.description,
            credits=credits,
            level=level,
            cross_listings=cross_listing_ids,
            declared_prerequisites=prereq_rules,
        )
        return course, edges

    except SchemaValidationError as exc:
        raise NormaliserError(raw.source_url, str(exc), exc) from exc
    except Exception as exc:
        raise NormaliserError(raw.source_url, f"Unexpected error: {exc}", exc) from exc


def _collect_course_ids(node: object) -> list[str]:
    """Recursively collect all course_id values from a predicate tree."""
    from granular.schema import AndList, OrList, SingleCourse
    if isinstance(node, SingleCourse):
        return [node.course_id]
    if isinstance(node, (AndList, OrList)):
        result: list[str] = []
        for child in node.children:
            result.extend(_collect_course_ids(child))
        return result
    return []


def normalise_programme(
    raw: RawProgramme,
    config: IngestConfig,
) -> Programme:
    """Convert a RawProgramme to a Programme record.

    Every requirement rule is either structured or marked not_machine_checkable.
    """
    provenance = ProvenanceRecord(
        source_url=raw.source_url,
        retrieved_at=raw.retrieved_at,
        adapter_name=config.adapter_name,
        adapter_version=config.adapter_version,
        source_revision=raw.source_revision,
    )

    level = ProgrammeLevel.GRADUATE if raw.level_raw.lower() == "graduate" else ProgrammeLevel.UNDERGRADUATE

    rules: list[RequirementRule] = []
    for i, raw_rule in enumerate(raw.requirement_rules):
        rule_type = RuleType.OTHER
        if raw_rule.rule_type_hint == "hours":
            rule_type = RuleType.MINIMUM_CREDITS
        elif raw_rule.rule_type_hint == "gpa":
            rule_type = RuleType.GPA_MINIMUM
        elif raw_rule.rule_type_hint == "courses":
            rule_type = RuleType.COURSE_LIST

        rules.append(
            RequirementRule(
                rule_id=f"rule-{i}",
                rule_type=rule_type,
                verbatim_text=raw_rule.verbatim_text,
                machine_checkable=False,  # all programme rules are not_machine_checkable for now
                structured_predicate=None,
            )
        )

    # Must have at least one rule
    if not rules:
        rules.append(
            RequirementRule(
                rule_id="rule-0",
                rule_type=RuleType.OTHER,
                verbatim_text="(no structured requirements found)",
                machine_checkable=False,
            )
        )

    programme_id = f"prog-{raw.name[:40].lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}"

    return Programme(
        provenance=provenance,
        programme_id=programme_id,
        authority=Authority.DERIVED,
        name=raw.name,
        level=level,
        department="Computer Science",
        catalogue_url=raw.source_url,
        requirement_rules=rules,
    )
