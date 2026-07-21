import json
import logging
import re
from typing import Any, Dict, Optional

LOG = logging.getLogger("jarvis.evolution.forge_pipeline")


def parse_forge_response(text: str) -> Dict[str, Any]:
    """Parse structured JSON from LLM response (raw JSON or fenced block)."""
    text = text.strip()
    if not text:
        return {"forge": False, "reason": "Empty LLM response"}

    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    LOG.warning("Could not parse forge JSON from LLM output.")
    return {"forge": False, "reason": "Unparseable LLM forge response"}


def validate_forge_proposal(data: Dict[str, Any]) -> Optional[str]:
    """Return error message if proposal invalid, else None."""
    if not data.get("forge"):
        return None
    for key in ("skill_name", "summary", "code", "test_command"):
        if not data.get(key):
            return f"Missing required field: {key}"
    return None
