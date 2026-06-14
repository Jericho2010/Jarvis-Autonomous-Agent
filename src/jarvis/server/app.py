import os
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List
import contextvars

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
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

@app.on_event("startup")
async def on_startup():
    await init_services()
    logger.info("JARVIS Server Online.")

class ChatRequest(BaseModel):
    message: str

@app.get("/v1/sessions")
async def list_sessions():
    await init_services()
    try:
        async with memory.db_path.parent.exists() and memory.db_path.exists() and asyncio.Lock():
            import aiosqlite
            async with aiosqlite.connect(memory.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute("SELECT id, started_at FROM sessions ORDER BY started_at DESC") as cursor:
                    rows = await cursor.fetchall()
                    return [{"session_id": r["id"], "started_at": r["started_at"]} for r in rows]
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

async def run_agent_turn(session_id: str, prompt: str):
    """Executes the agent turn in a background task and streams updates."""
    # Set the ContextVar for the current task so tool telemetry knows the session_id
    current_session_id.set(session_id)
    
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
    asyncio.create_task(run_agent_turn(session_id, req.message))
    return {"status": "submitted"}

@app.get("/v1/sessions/{session_id}/stream")
async def stream_session(session_id: str, request: Request):
    await init_services()
    
    # Create an SSE event queue for this subscriber connection
    q = asyncio.Queue()
    session_broadcasters.setdefault(session_id, []).append(q)
    
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
                if q in session_broadcasters[session_id]:
                    session_broadcasters[session_id].remove(q)
                if not session_broadcasters[session_id]:
                    del session_broadcasters[session_id]
                    
    return StreamingResponse(sse_generator(), media_type="text/event-stream")

def import_json_str(data: dict) -> str:
    import json
    return json.dumps(data)
