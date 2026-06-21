from datetime import datetime

from agent_framework import tool

from jarvis.config.paths import get_db_path
from jarvis.memory.memory_manager import MemoryManager


@tool(approval_mode="never_require")
async def recall_past_chats(query: str, limit: int = 8) -> str:
    """Search Jarvis chat history across all sessions when Shaun references past work or decisions."""
    memory = MemoryManager(get_db_path())
    await memory.init_db()
    results = await memory.search_messages(query, limit=limit)
    if not results:
        return f"No past chats matched: {query!r}"

    lines = [f"Found {len(results)} match(es) for {query!r}:"]
    for r in results:
        ts = r.get("timestamp")
        when = ""
        if ts:
            try:
                when = datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
            except (TypeError, ValueError, OSError):
                when = str(ts)
        snippet = r.get("snippet") or ""
        content = r.get("content") or ""
        excerpt = snippet if snippet else (content[:200] + "…" if len(content) > 200 else content)
        lines.append(
            f"- [{when}] session={r.get('session_id')} role={r.get('role')}: {excerpt}"
        )
    return "\n".join(lines)
