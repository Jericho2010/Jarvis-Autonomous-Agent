import os
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import contextvars

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from jarvis.memory.memory_manager import MemoryManager
from jarvis.core.agent import create_jarvis_agent, DEFAULT_SYSTEM_PROMPT
from jarvis.skills.skill_forge import load_skills_from_dir, forge_skill
from jarvis.core.subagents import current_session_id, session_broadcasters, broadcast_event, sys_session_send

# Configure logging
logging.basicConfig(
    filename="/home/shaun/jarvis/data/server.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("jarvis.server")

app = FastAPI(title="JARVIS API Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "jarvis"}


# Lazy initialized database manager
db_path = os.environ.get("JARVIS_DB_PATH", "/home/shaun/jarvis/data/jarvis.db")
memory = MemoryManager(Path(db_path))

# Global startup lock
startup_lock = asyncio.Lock()
initialized = False

async def init_services():
    global initialized
    async with startup_lock:
        if not initialized:
            await memory.init_db()
            initialized = True

def check_system_dependencies():
    import shutil
    missing = []
    for cmd in ["xdotool", "scrot", "wmctrl"]:
        if not shutil.which(cmd):
            missing.append(cmd)
    try:
        import playwright
    except ImportError:
        missing.append("playwright (python package)")
        
    if missing:
        from rich.console import Console
        console = Console()
        console.print(f"\n[bold #FFD700]⚠ Stark System Diagnostics // Missing dependencies: {', '.join(missing)}[/bold #FFD700]")
        console.print("[dim #FFD700]Please run: sudo apt install scrot xdotool wmctrl && playwright install[/dim]\n")
        logger.warning(f"Startup Diagnostics: Missing dependencies {missing}")

@app.on_event("startup")
async def on_startup():
    await init_services()
    check_system_dependencies()
    logger.info("JARVIS Server Online.")

class ChatRequest(BaseModel):
    message: str
    client_id: Optional[str] = None

@app.get("/v1/sessions")
async def list_sessions():
    await init_services()
    try:
        import time
        import aiosqlite
        async with aiosqlite.connect(memory.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            # 1. Delete stale empty sessions older than 1 hour
            one_hour_ago = time.time() - 3600
            await conn.execute(
                "DELETE FROM sessions WHERE id NOT IN (SELECT DISTINCT session_id FROM messages) AND started_at < ?",
                (one_hour_ago,)
            )
            await conn.commit()
            
            # 2. Get sessions that have messages
            query = """
                SELECT DISTINCT s.id, s.started_at, s.model 
                FROM sessions s
                JOIN messages m ON s.id = m.session_id
                ORDER BY s.started_at DESC
            """
            async with conn.execute(query) as cursor:
                rows = await cursor.fetchall()
                
            # If no sessions have messages, return the most recent session
            if not rows:
                async with conn.execute("SELECT id, started_at, model FROM sessions ORDER BY started_at DESC LIMIT 1") as cursor:
                    rows = await cursor.fetchall()
                    
            return [{"session_id": r["id"], "started_at": r["started_at"], "model": r["model"] or "house-party"} for r in rows]
    except Exception as e:
        logger.exception("Failed to list sessions")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/sessions")
async def create_session():
    await init_services()
    try:
        import random
        session_id = f"session_{int(asyncio.get_event_loop().time())}_{random.randint(1000, 9999)}"
        
        # We pre-compile system instructions to record in the sessions table
        profile = await memory.build_profile_prompt()
        soul_body = ""
        soul_file = Path("/home/shaun/jarvis/skills/jarvis_soul/SKILL.md")
        if soul_file.exists():
            content = soul_file.read_text(encoding="utf-8")
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    soul_body = parts[2].strip()
            else:
                soul_body = content.strip()
                
        custom_instructions = f"{DEFAULT_SYSTEM_PROMPT}"
        if soul_body:
            custom_instructions += f"\n\n# ACTIVE PERSONA PROFILE\n{soul_body}"
        custom_instructions += f"\n\n{profile}"
        
        await memory.create_session(
            session_id=session_id,
            model="house-party",
            system_prompt=custom_instructions
        )
        logger.info(f"Created new session: {session_id}")
        return {"session_id": session_id}
    except Exception as e:
        logger.exception("Failed to create session")
        raise HTTPException(status_code=500, detail=str(e))

async def run_agent_turn(session_id: str, prompt: str, exclude_client_id: Optional[str] = None):
    """Executes the agent turn in a background task and streams updates."""
    # Set the ContextVar for the current task so tool telemetry knows the session_id
    current_session_id.set(session_id)
    
    # Broadcast the user prompt to all other clients subscribed to the stream
    import time
    await broadcast_event(session_id, "user_message", {"text": prompt, "timestamp": time.time()}, exclude_client_id=exclude_client_id)
    
    try:
        # 1. Add user message to SQLite memory
        await memory.add_message(session_id, "user", prompt)
        
        # 2. Compile instructions and active tools
        profile = await memory.build_profile_prompt()
        soul_body = ""
        soul_file = Path("/home/shaun/jarvis/skills/jarvis_soul/SKILL.md")
        if soul_file.exists():
            content = soul_file.read_text(encoding="utf-8")
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    soul_body = parts[2].strip()
            else:
                soul_body = content.strip()
                
        custom_instructions = f"{DEFAULT_SYSTEM_PROMPT}"
        if soul_body:
            custom_instructions += f"\n\n# ACTIVE PERSONA PROFILE\n{soul_body}"
        custom_instructions += f"\n\n{profile}"
        
        skills_tools = load_skills_from_dir(Path("/home/shaun/jarvis/skills"))
        all_tools = [forge_skill, sys_session_send] + skills_tools
        
        # 3. Create J.A.R.V.I.S. Core agent
        agent = create_jarvis_agent(
            api_key=os.environ.get("NVIDIA_API_KEY", ""),
            instructions_override=custom_instructions,
            tools=all_tools
        )
        
        # Fetch session model from SQLite
        session_model = "house-party"
        try:
            import aiosqlite
            async with aiosqlite.connect(memory.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute("SELECT model FROM sessions WHERE id = ?", (session_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row and row["model"]:
                        session_model = row["model"]
        except Exception:
            logger.exception("Failed to fetch session model")
            
        if session_model:
            agent.client.primary_model = session_model
        
        # 4. Fetch full history to feed the agent
        history_msgs = await memory.get_session_history(session_id)
        from agent_framework._types import Message
        agent_msgs = []
        for m in history_msgs:
            agent_msgs.append(Message(role=m["role"], contents=[m["content"] or ""]))
            
        # 5. Run agent stream
        raw_buffer = ""
        last_reasoning = ""
        last_text = ""
        accumulated_text = ""
        
        async for chunk in agent.run(messages=agent_msgs, stream=True):
            if chunk.text:
                raw_buffer += chunk.text
                
                # Dynamic parsing of <think> tags
                if "<think>" in raw_buffer:
                    if "</think>" in raw_buffer:
                        parts = raw_buffer.split("<think>", 1)
                        before_think = parts[0]
                        think_and_after = parts[1].split("</think>", 1)
                        current_reasoning = think_and_after[0].strip()
                        current_text = before_think + think_and_after[1]
                    else:
                        parts = raw_buffer.split("<think>", 1)
                        current_reasoning = parts[1].strip()
                        current_text = parts[0]
                else:
                    current_reasoning = ""
                    current_text = raw_buffer
                
                # Emit increments
                if current_reasoning != last_reasoning:
                    diff = current_reasoning[len(last_reasoning):]
                    await broadcast_event(session_id, "reasoning_chunk", {"text": diff})
                    last_reasoning = current_reasoning
                    
                if current_text != last_text:
                    diff = current_text[len(last_text):]
                    await broadcast_event(session_id, "text_chunk", {"text": diff})
                    last_text = current_text
                    
        # 6. Turn completion
        if last_reasoning:
            accumulated_text += f"<think>\n{last_reasoning}\n</think>\n"
        accumulated_text += last_text
        
        if accumulated_text.strip():
            await memory.add_message(session_id, "assistant", accumulated_text)
            
        await broadcast_event(session_id, "turn_complete", {"session_id": session_id})
        logger.info(f"Session {session_id} turn completed successfully.")
        
    except Exception as e:
        logger.exception(f"Error executing agent turn for session {session_id}")
        await broadcast_event(session_id, "text_chunk", {"text": f"\n\n[bold red]System Error:[/] {e}\n"})
        await broadcast_event(session_id, "turn_complete", {"session_id": session_id})

@app.post("/v1/sessions/{session_id}/chat")
async def post_message(session_id: str, req: ChatRequest):
    await init_services()
    # Start task in background to process and stream via SSE
    asyncio.create_task(run_agent_turn(session_id, req.message, exclude_client_id=req.client_id))
    return {"status": "submitted"}

@app.get("/v1/sessions/{session_id}/stream")
async def stream_session(session_id: str, request: Request, client_id: Optional[str] = None):
    await init_services()
    
    # Create an SSE event queue for this subscriber connection
    q = asyncio.Queue()
    session_broadcasters.setdefault(session_id, []).append({"queue": q, "client_id": client_id})
    
    async def sse_generator():
        try:
            # Yield connection confirmation
            yield "event: connection_confirmed\ndata: {}\n\n"
            
            while True:
                try:
                    event_data = await asyncio.wait_for(q.get(), timeout=10.0)
                    yield f"event: {event_data['event']}\ndata: {import_json_str(event_data['data'])}\n\n"
                except asyncio.TimeoutError:
                    # Ping connection to keep it alive
                    yield "event: ping\ndata: {}\n\n"
        finally:
            # Cleanup subscriber
            if session_id in session_broadcasters:
                session_broadcasters[session_id] = [
                    sub for sub in session_broadcasters[session_id] if sub["queue"] != q
                ]
                if not session_broadcasters[session_id]:
                    del session_broadcasters[session_id]
                    
    return StreamingResponse(sse_generator(), media_type="text/event-stream")

@app.get("/v1/sessions/{session_id}")
async def get_session_detail(session_id: str):
    await init_services()
    try:
        import aiosqlite
        async with aiosqlite.connect(memory.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT id, model, started_at FROM sessions WHERE id = ?", (session_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {"session_id": row["id"], "model": row["model"] or "house-party", "started_at": row["started_at"]}
                raise HTTPException(status_code=404, detail="Session not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get session details")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/sessions/{session_id}/history")
async def get_session_history_endpoint(session_id: str):
    await init_services()
    try:
        import time
        msgs = await memory.get_session_history(session_id)
        formatted = []
        for m in msgs:
            role = m["role"]
            content = m["content"] or ""
            reasoning = ""
            if role == "assistant" and "<think>" in content:
                parts = content.split("<think>", 1)
                before_think = parts[0]
                if "</think>" in parts[1]:
                    think_parts = parts[1].split("</think>", 1)
                    reasoning = think_parts[0].strip()
                    content = (before_think + think_parts[1]).strip()
                else:
                    reasoning = parts[1].strip()
                    content = before_think.strip()
            formatted.append({
                "role": role,
                "content": content,
                "reasoning": reasoning,
                "timestamp": int(m["timestamp"] * 1000) if m.get("timestamp") else int(time.time() * 1000)
            })
        return formatted
    except Exception as e:
        logger.exception("Failed to get session history")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/models")
async def list_models():
    from jarvis.core.agent import NIM_MODEL_BASKET
    return {"models": ["house-party"] + NIM_MODEL_BASKET}

class ModelUpdateRequest(BaseModel):
    model: str

@app.post("/v1/sessions/{session_id}/model")
async def update_session_model(session_id: str, req: ModelUpdateRequest):
    await init_services()
    try:
        import aiosqlite
        async with aiosqlite.connect(memory.db_path) as conn:
            await conn.execute("UPDATE sessions SET model = ? WHERE id = ?", (req.model, session_id))
            await conn.commit()
        logger.info(f"Updated session {session_id} model to {req.model}")
        return {"status": "success", "model": req.model}
    except Exception as e:
        logger.exception("Failed to update session model")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/subagents/{name}")
async def get_subagent_detail(name: str):
    name_clean = name.lower().strip()
    if name_clean not in ("friday", "homer", "plato"):
        raise HTTPException(status_code=404, detail=f"Subagent '{name}' not found")
    try:
        from pathlib import Path
        from jarvis.core.subagents import parse_simple_yaml
        from jarvis.skills.skill_forge import load_skills_from_dir
        
        subagent_dir = Path(f"/home/shaun/jarvis/skills/{name_clean}")
        config_file = subagent_dir / "config.yaml"
        soul_file = subagent_dir / f"{name_clean}_soul.md"
        
        if not config_file.exists() or not soul_file.exists():
            raise HTTPException(status_code=404, detail="Subagent configuration missing")
            
        config = parse_simple_yaml(config_file.read_text(encoding="utf-8"))
        instructions = soul_file.read_text(encoding="utf-8").strip()
        
        model = config.get("model", "house-party")
        tools_list = load_skills_from_dir(subagent_dir)
        tools = [{"name": t.name, "description": t.description} for t in tools_list]
        
        return {
            "name": name_clean.upper(),
            "model": model,
            "instructions": instructions,
            "tools": tools
        }
    except Exception as e:
        logger.exception(f"Failed to load subagent {name}")
        raise HTTPException(status_code=500, detail=str(e))

def import_json_str(data: dict) -> str:
    import json
    return json.dumps(data)

# Serve built React Web UI at "/"
web_ui_dist = Path("/home/shaun/jarvis/web/dist")
if web_ui_dist.is_dir() and (web_ui_dist / "index.html").is_file():
    app.mount("/", StaticFiles(directory=str(web_ui_dist), html=True), name="web-ui")
