"""SeedWriter — write bootstrapped KnowledgeUnit records to the vocabulary seed file."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from granular.extraction.bootstrap.pdf_parser import ParsedKU, _KNOWN_AREAS
from granular.schema import KnowledgeTier, KnowledgeUnit

logger = logging.getLogger(__name__)


def build_knowledge_units(parsed: list[ParsedKU]) -> list[KnowledgeUnit]:
    """Convert ParsedKU records to canonical KnowledgeUnit schema objects."""
    units: list[KnowledgeUnit] = []
    for p in parsed:
        tier = KnowledgeTier.CORE if p.tier == "core" else KnowledgeTier.ELECTIVE
        units.append(
            KnowledgeUnit(
                ku_id=p.ku_id,
                label=p.label,
                knowledge_area=p.knowledge_area_code,
                tier=tier,
                source="CS2023",
            )
        )
    return units


def write_seed(units: list[KnowledgeUnit], output_path: Path) -> None:
    """Write knowledge units to the versioned seed JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Group by knowledge area for readability
    by_area: dict[str, list[dict]] = {}
    for ku in units:
        entry = {
            "ku_id": ku.ku_id,
            "label": ku.label,
            "knowledge_area": ku.knowledge_area,
            "knowledge_area_name": _KNOWN_AREAS.get(ku.knowledge_area, ku.knowledge_area),
            "tier": ku.tier.value,
            "source": ku.source,
        }
        by_area.setdefault(ku.knowledge_area, []).append(entry)

    ka_count = len(by_area)
    ku_count = len(units)

    payload = {
        "source": "CS2023",
        "extracted_at": datetime.now(tz=timezone.utc).isoformat(),
        "knowledge_area_count": ka_count,
        "knowledge_unit_count": ku_count,
        "units": [entry for entries in by_area.values() for entry in entries],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    logger.info(
        "Wrote %d knowledge units across %d areas to %s",
        ku_count,
        ka_count,
        output_path,
    )


def load_seed(path: Path) -> list[KnowledgeUnit]:
    """Load KnowledgeUnit records from the seed JSON file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    units: list[KnowledgeUnit] = []
    for entry in data.get("units", []):
        tier = KnowledgeTier.CORE if entry["tier"] == "core" else KnowledgeTier.ELECTIVE
        units.append(
            KnowledgeUnit(
                ku_id=entry["ku_id"],
                label=entry["label"],
                knowledge_area=entry["knowledge_area"],
                tier=tier,
                source="CS2023",
            )
        )
    return units
