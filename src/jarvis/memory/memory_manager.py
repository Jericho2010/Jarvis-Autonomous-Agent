import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import aiosqlite

logger = logging.getLogger("jarvis.memory")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    model TEXT,
    system_prompt TEXT,
    title TEXT,
    agent_id TEXT DEFAULT 'jarvis',
    started_at REAL NOT NULL,
    ended_at REAL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    tool_name TEXT,
    tool_calls TEXT,
    timestamp REAL NOT NULL,
    active INTEGER DEFAULT 1,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS facts (
    category TEXT NOT NULL,
    subject TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (category, subject)
);

CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    tool_name,
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content, tool_name) VALUES (
        new.id,
        COALESCE(new.content, ''),
        COALESCE(new.tool_name, '')
    );
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
    DELETE FROM messages_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages BEGIN
    DELETE FROM messages_fts WHERE rowid = old.id;
    INSERT INTO messages_fts(rowid, content, tool_name) VALUES (
        new.id,
        COALESCE(new.content, ''),
        COALESCE(new.tool_name, '')
    );
END;
"""

class MemoryManager:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def init_db(self):
        """Initializes tables, indexes and FTS5 triggers."""
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.executescript(SCHEMA)
            
            # Dynamic schema migrations for existing database files
            try:
                await conn.execute("ALTER TABLE sessions ADD COLUMN title TEXT")
                await conn.commit()
            except sqlite3.OperationalError:
                pass
            try:
                await conn.execute("ALTER TABLE sessions ADD COLUMN agent_id TEXT DEFAULT 'jarvis'")
                await conn.commit()
            except sqlite3.OperationalError:
                pass
            
            # Check FTS5 support
            try:
                await conn.executescript(FTS_SCHEMA)
            except sqlite3.OperationalError as e:
                logger.warning(f"SQLite FTS5 initialization failed (FTS5 module missing): {e}")

    async def create_session(self, session_id: str, model: str, system_prompt: str, title: Optional[str] = None, agent_id: str = "jarvis") -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "INSERT INTO sessions (id, model, system_prompt, title, agent_id, started_at) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, model, system_prompt, title, agent_id, time.time()),
            )
            await conn.commit()

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_name: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        tool_calls_json = json.dumps(tool_calls) if tool_calls else None
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                """INSERT INTO messages 
                   (session_id, role, content, tool_name, tool_calls, timestamp) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, role, content, tool_name, tool_calls_json, time.time()),
            )
            msg_id = cursor.lastrowid
            await conn.commit()
            return msg_id or 0

    async def get_session_history(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM messages WHERE session_id = ? AND active = 1 ORDER BY timestamp ASC LIMIT ?",
                (session_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                result = []
                for r in rows:
                    t_calls = None
                    if r["tool_calls"]:
                        try:
                            t_calls = json.loads(r["tool_calls"])
                        except Exception:
                            pass
                    result.append({
                        "id": r["id"],
                        "role": r["role"],
                        "content": r["content"],
                        "tool_name": r["tool_name"],
                        "tool_calls": t_calls,
                        "timestamp": r["timestamp"]
                    })
                return result

    async def search_messages(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Searches past messages across all sessions using SQLite FTS5."""
        if not query.strip():
            return []
        # Sanitize query keywords
        sanitized = " ".join([f'"{w}"' for w in query.replace('"', '').split() if w])
        if not sanitized:
            return []
            
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            sql = """
                SELECT 
                    m.id, m.session_id, m.role, m.content, m.timestamp,
                    snippet(messages_fts, 0, '>>>', '<<<', '...', 20) as snippet
                FROM messages m
                JOIN messages_fts f ON m.id = f.rowid
                WHERE messages_fts MATCH ? AND m.active = 1
                ORDER BY rank LIMIT ?
            """
            try:
                async with conn.execute(sql, (sanitized, limit)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(r) for r in rows]
            except sqlite3.OperationalError as e:
                # Fallback to LIKE if FTS5 fails or is disabled
                logger.warning(f"FTS5 query failed, falling back to LIKE: {e}")
                fallback_sql = """
                    SELECT id, session_id, role, content, timestamp, '' as snippet
                    FROM messages
                    WHERE (content LIKE ? OR tool_name LIKE ?) AND active = 1
                    ORDER BY timestamp DESC LIMIT ?
                """
                like_query = f"%{query}%"
                async with conn.execute(fallback_sql, (like_query, like_query, limit)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(r) for r in rows]

    async def upsert_fact(self, category: str, subject: str, value: Any) -> None:
        val_str = json.dumps(value) if not isinstance(value, str) else value
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """INSERT INTO facts (category, subject, value, created_at) 
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(category, subject) DO UPDATE SET value=excluded.value, created_at=excluded.created_at""",
                (category, subject, val_str, time.time()),
            )
            await conn.commit()

    async def get_facts(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            if category:
                sql = "SELECT * FROM facts WHERE category = ? ORDER BY created_at DESC"
                params = (category,)
            else:
                sql = "SELECT * FROM facts ORDER BY category, created_at DESC"
                params = ()
            async with conn.execute(sql, params) as cursor:
                rows = await cursor.fetchall()
                res = []
                for r in rows:
                    try:
                        val = json.loads(r["value"])
                    except Exception:
                        val = r["value"]
                    res.append({
                        "category": r["category"],
                        "subject": r["subject"],
                        "value": val,
                        "created_at": r["created_at"]
                    })
                return res

    async def upsert_preference(self, key: str, value: Any) -> None:
        val_str = json.dumps(value) if not isinstance(value, str) else value
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """INSERT INTO preferences (key, value, updated_at) 
                   VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (key, val_str, time.time()),
            )
            await conn.commit()

    async def get_preferences(self) -> Dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM preferences") as cursor:
                rows = await cursor.fetchall()
                res = {}
                for r in rows:
                    try:
                        res[r["key"]] = json.loads(r["value"])
                    except Exception:
                        res[r["key"]] = r["value"]
                return res

    async def build_profile_prompt(self) -> str:
        """Compiles facts and preferences into a consolidated system prompt segment."""
        prefs = await self.get_preferences()
        facts = await self.get_facts()
        
        lines = []
        if prefs:
            lines.append("## USER PREFERENCES")
            for k, v in prefs.items():
                lines.append(f"- {k}: {v}")
        
        if facts:
            lines.append("## COMPILED OPERATIONAL FACTS")
            # Group facts by category
            cats: Dict[str, List[str]] = {}
            for f in facts:
                cats.setdefault(f["category"], []).append(f"{f['subject']}: {f['value']}")
            for cat, items in cats.items():
                lines.append(f"### {cat.upper()}")
                for item in items:
                    lines.append(f"- {item}")
        
        return "\n".join(lines) if lines else "No compiled preference profile available yet."

    async def update_session_title(self, session_id: str, title: str) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "UPDATE sessions SET title = ? WHERE id = ?",
                (title, session_id),
            )
            await conn.commit()

    async def update_session_agent(self, session_id: str, agent_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "UPDATE sessions SET agent_id = ? WHERE id = ?",
                (agent_id, session_id),
            )
            await conn.commit()

