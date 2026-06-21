"""Session-end memory extraction: summary + durable facts."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from agent_framework._types import Message

from jarvis.config.models import apply_primary_model
from jarvis.core.agent import StarkNIMChatClient
from jarvis.memory.memory_manager import MemoryManager

LOG = logging.getLogger("jarvis.memory.extractor")

MAX_TRANSCRIPT_MESSAGES = 40
MAX_MESSAGE_CHARS = 600

EXTRACT_PROMPT = """Analyze this Jarvis session transcript. Return JSON only:
{{
  "session_summary": "2-4 sentences: what was discussed and key outcomes",
  "facts": [
    {{"category": "user|project|decision|environment", "subject": "stable_snake_key", "value": "concise durable fact"}}
  ]
}}

Rules:
- facts: 0 to 3 items; only durable truths (identity, active projects, decisions, environment)
- skip jokes, banter, greetings, one-off tangents
- session_summary required when transcript is non-empty
- subject keys like user/name, project/jarvis/status, decision/homer_for_web

Transcript:
{transcript}
"""


def _strip_thinking(content: str) -> str:
    if "<think>" in content and "</think>" in content:
        return content.split("</think>", 1)[1].strip()
    return content


def _format_transcript(messages: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for m in messages[-MAX_TRANSCRIPT_MESSAGES:]:
        role = m.get("role", "")
        raw = m.get("content") or ""
        text = _strip_thinking(raw).strip()
        if not text:
            continue
        if len(text) > MAX_MESSAGE_CHARS:
            text = text[:MAX_MESSAGE_CHARS] + "…"
        label = "User" if role == "user" else "Jarvis"
        lines.append(f"{label}: {text}")
    return "\n".join(lines)


def _parse_extract_response(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
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
    return {}


async def finalize_session(
    memory: MemoryManager,
    session_id: str,
    *,
    api_key: str,
) -> bool:
    """Summarize a session and upsert durable facts. Returns True if work was done."""
    if await memory.is_session_finalized(session_id):
        return False

    messages = await memory.get_session_history(session_id, limit=MAX_TRANSCRIPT_MESSAGES)
    if not messages:
        await memory.mark_session_ended(session_id)
        return False

    transcript = _format_transcript(messages)
    if not transcript.strip():
        await memory.mark_session_ended(session_id)
        return False

    summary = ""
    facts: List[Dict[str, Any]] = []

    if api_key:
        try:
            client = StarkNIMChatClient(api_key=api_key)
            apply_primary_model(client, "house-party")
            prompt = EXTRACT_PROMPT.format(transcript=transcript)
            resp = await client.get_response(
                [Message(role="user", contents=[prompt])],
                options={"temperature": 0.2, "response_format": {"type": "json_object"}},
            )
            raw = resp.messages[0].contents[0].text if resp.messages else ""
            parsed = _parse_extract_response(raw)
            summary = (parsed.get("session_summary") or "").strip()
            raw_facts = parsed.get("facts") or []
            if isinstance(raw_facts, list):
                facts = [f for f in raw_facts if isinstance(f, dict)][:3]
        except Exception:
            LOG.exception("Session memory extraction failed for %s", session_id)

    if not summary:
        user_bits = [
            _strip_thinking(m["content"] or "")[:120]
            for m in messages
            if m.get("role") == "user" and (m.get("content") or "").strip()
        ]
        if user_bits:
            summary = f"Session covered: {'; '.join(user_bits[:3])}"
        else:
            summary = "Brief Jarvis session with no durable user requests recorded."

    await memory.upsert_fact("session_summary", session_id, summary)

    allowed = {"user", "project", "decision", "environment"}
    for fact in facts:
        cat = str(fact.get("category", "")).strip().lower()
        subj = str(fact.get("subject", "")).strip()
        val = fact.get("value")
        if cat not in allowed or not subj or val is None:
            continue
        await memory.upsert_fact(cat, subj, val)

    await memory.mark_session_ended(session_id)
    clear_workflow_state(session_id)
    LOG.info("Finalized session memory for %s (%d facts)", session_id, len(facts))
    return True


def clear_workflow_state(session_id: str) -> None:
    try:
        from jarvis.core.handoff_workflow import clear_workflow_state as _clear

        _clear(session_id)
    except Exception:
        pass
