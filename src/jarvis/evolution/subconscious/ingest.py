import json
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import aiosqlite

from jarvis.memory.memory_manager import MemoryManager

LOG = logging.getLogger("jarvis.evolution.ingest")

TOOL_OUTPUT_MAX = 400
ASSISTANT_SNIPPET_MAX = 200


def _strip_thinking(content: str) -> str:
    if "<think>" in content and "</think>" in content:
        return content.split("</think>", 1)[1].strip()
    return content


async def gather_dream_context(memory: MemoryManager) -> Dict[str, Any]:
    """Collect 24h messages, facts, preferences, and tool context for Dream."""
    now = datetime.now()
    since_ts = (now - timedelta(hours=24)).timestamp()

    shards: List[str] = []
    if memory.db_path.exists():
        async with aiosqlite.connect(memory.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT role, content, tool_name FROM messages WHERE timestamp >= ? AND active = 1",
                (since_ts,),
            ) as cursor:
                rows = await cursor.fetchall()
                for r in rows:
                    role = r["role"]
                    content = r["content"] or ""
                    if role == "user":
                        shards.append(f"USER: {content[:500]}")
                    elif role == "assistant":
                        clean = _strip_thinking(content)[:ASSISTANT_SNIPPET_MAX]
                        shards.append(f"JARVIS: {clean}")
                    elif role == "tool" or r["tool_name"]:
                        tool = r["tool_name"] or "tool"
                        shards.append(f"TOOL {tool}: {content[:TOOL_OUTPUT_MAX]}")
                    elif r["tool_name"]:
                        shards.append(f"TOOL CALL: {r['tool_name']}")

    random.shuffle(shards)
    memory_soup = "\n".join(shards[:100])
    if not memory_soup:
        memory_soup = "The workshop was quiet today. No user messages were recorded in the logs."

    facts = await memory.get_facts()
    preferences = await memory.get_preferences()

    facts_lines = []
    for f in facts[:40]:
        val = f["value"]
        if not isinstance(val, str):
            val = json.dumps(val)[:200]
        facts_lines.append(f"- [{f['category']}] {f['subject']}: {val}")

    pref_lines = [f"- {k}: {v}" for k, v in list(preferences.items())[:20]]

    return {
        "memory_soup": memory_soup,
        "facts_block": "\n".join(facts_lines) if facts_lines else "No stored facts.",
        "preferences_block": "\n".join(pref_lines) if pref_lines else "No stored preferences.",
    }
