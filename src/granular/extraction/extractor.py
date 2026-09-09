"""ConceptExtractor — extract atomic concepts from a course description via LLM.

One structured LLM call per course. Returns a list of RawConcept records.
The model is told to extract only concepts explicitly stated or strongly implied
in the description, at CS2023 knowledge-unit grain.

Critical: metadata (course number, department, level) is NOT appended to the
prompt text. The model sees only the description.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from granular.extraction.llm import get_model_name, get_provider

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a computer science curriculum analyst. Extract atomic knowledge concepts
from the provided course description.

Rules:
- Extract only concepts explicitly stated or strongly implied in the description.
- Each concept should be at the grain of a CS2023 knowledge unit — specific enough
  to be a distinct learning outcome (e.g. "maximum likelihood estimation",
  "binary search trees", "TCP/IP protocol stack"), not broad ("algorithms").
- Do NOT infer from the course number, title, or department. Use only the description text.
- Return a JSON array of objects with a single "label" string field.
- If no concepts can be extracted, return an empty array [].

Example output:
[
  {"label": "binary search trees"},
  {"label": "heap sort"},
  {"label": "amortized complexity analysis"}
]
"""


@dataclass
class RawConcept:
    label: str
    source_course_id: str
    model_id: str


class ConceptExtractor:
    """Extract atomic concepts from course descriptions using an LLM."""

    def __init__(self, model_id: str) -> None:
        self._model_id = model_id
        self._provider = get_provider(model_id)

    def extract(self, course_id: str, description: str) -> list[RawConcept]:
        """Extract concepts from a course description.

        Returns empty list on failure (logged). Never raises.
        """
        if not description or len(description.strip()) < 20:
            logger.info("Skipping extraction for %s: description too short", course_id)
            return []

        model = get_model_name(self._model_id)

        try:
            response = self._provider.chat_completion(
                system=_SYSTEM_PROMPT,
                user_message=description.strip(),
                model=model,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            raw_json = response or "[]"
            # The model may return {"concepts": [...]} or just [...]
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict):
                items = parsed.get("concepts", parsed.get("labels", list(parsed.values())[0] if parsed else []))
            else:
                items = parsed

            if not isinstance(items, list):
                logger.warning("LLM returned non-list for %s; got %r", course_id, type(items))
                return []

            concepts: list[RawConcept] = []
            for item in items:
                label = ""
                if isinstance(item, dict):
                    label = item.get("label", "").strip()
                elif isinstance(item, str):
                    label = item.strip()
                if label:
                    concepts.append(
                        RawConcept(
                            label=label,
                            source_course_id=course_id,
                            model_id=self._model_id,
                        )
                    )

            logger.debug("Extracted %d concepts from %s", len(concepts), course_id)
            return concepts

        except json.JSONDecodeError as exc:
            logger.warning("LLM returned malformed JSON for %s: %s", course_id, exc)
            return []
        except Exception as exc:
            logger.warning("LLM call failed for %s: %s", course_id, exc)
            return []
