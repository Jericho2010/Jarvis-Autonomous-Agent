import os
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import contextvars

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

from jarvis.config.models import (
    NIM_MODEL_BASKET,
    apply_primary_model,
    is_house_party,
    normalize_session_model,
)
from jarvis.config.paths import (
    get_data_dir,
    get_db_path,
    get_env_file,
    get_skills_dir,
    get_subagent_dir,
    get_web_dist_dir,
    get_webvision_dir,
)
from jarvis.config.nvidia import (
    format_missing_basket_warning,
    format_nvidia_speech_error,
    missing_basket_model_ids,
    nvidia_api_key_problem,
)
from jarvis.memory.memory_manager import MemoryManager
from jarvis.memory.extractor import finalize_session
from jarvis.core.agent import create_jarvis_agent, DEFAULT_SYSTEM_PROMPT
from jarvis.core.display_env import log_startup_display_warning
from jarvis.core.system_deps import check_system_dependencies
from jarvis.core.handoff_workflow import clear_workflow_state, run_handoff_turn, submit_approval
from jarvis.core.playwright_mcp import get_playwright_mcp_manager
from jarvis.skills.skill_forge import load_skills_from_dir, forge_skill
from jarvis.core.subagents import current_session_id, session_broadcasters, broadcast_event
from jarvis.config.voice import VOICE_MODE_PREF_KEY, VOICE_MODE_SYSTEM_APPEND
from jarvis.voice.nim_speech import clean_text_for_speech, get_speech_client

load_dotenv(get_env_file())

# Configure logging
logging.basicConfig(
    filename=str(get_data_dir() / "server.log"),
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


class NoCacheIndexMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path in ("", "/", "/index.html"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


app.add_middleware(NoCacheIndexMiddleware)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "jarvis"}


# Lazy initialized database manager
memory = MemoryManager(get_db_path())

# Global startup lock
startup_lock = asyncio.Lock()
initialized = False

# Serialize turns per session so TUI + Web cannot interleave history writes.
_session_turn_locks: Dict[str, asyncio.Lock] = {}


def _session_turn_lock(session_id: str) -> asyncio.Lock:
    lock = _session_turn_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _session_turn_locks[session_id] = lock
    return lock


async def init_services():
    global initialized, memory
    async with startup_lock:
        current_env_path = str(get_db_path())
        if not initialized or str(memory.db_path) != current_env_path:
            memory = MemoryManager(get_db_path())
            await memory.init_db()
            initialized = True


async def _probe_nim_basket_at_startup() -> None:
    api_key = os.environ.get("NVIDIA_API_KEY", "")
    if nvidia_api_key_problem(api_key):
        logger.warning("Skipping NIM basket health probe: %s", nvidia_api_key_problem(api_key))
        return
    missing = await missing_basket_model_ids(NIM_MODEL_BASKET, api_key)
    if missing:
        logger.warning(format_missing_basket_warning(missing))
    else:
        logger.info(
            "NIM basket health: all %d models present on integrate.api.nvidia.com",
            len(NIM_MODEL_BASKET),
        )


@app.on_event("startup")
async def on_startup():
    await init_services()
    # Voice mode always starts disabled; Shaun re-enables it per session via /voicemode on.
    await memory.upsert_preference(VOICE_MODE_PREF_KEY, False)
    check_system_dependencies()
    log_startup_display_warning()
    await _probe_nim_basket_at_startup()
    manager = get_playwright_mcp_manager()
    ok, detail = manager.node_version_ok()
    if ok:
        try:
            await manager.start()
        except Exception as exc:
            logger.warning("Playwright MCP failed to start at boot: %s", exc)
    else:
        logger.warning("Playwright MCP skipped: %s", detail)
    logger.info("JARVIS Server Online.")

@app.on_event("shutdown")
async def on_shutdown():
    await get_playwright_mcp_manager().stop()

class ChatRequest(BaseModel):
    message: str
    client_id: Optional[str] = None
    files: Optional[List[dict]] = None

class AgentSwitchRequest(BaseModel):
    agent_id: str

class VoiceModeRequest(BaseModel):
    enabled: bool

class VoiceTTSRequest(BaseModel):
    text: str

class ApprovalRequest(BaseModel):
    request_id: str
    approved: bool

class CreateSessionRequest(BaseModel):
    finalize_session_id: Optional[str] = None


def schedule_session_finalize(session_id: Optional[str]) -> None:
    if not session_id:
        return
    # Drop in-process workflow immediately; finalize also clears after persistence.
    clear_workflow_state(session_id)
    api_key = os.environ.get("NVIDIA_API_KEY", "")

    async def _run() -> None:
        try:
            await finalize_session(memory, session_id, api_key=api_key)
        except Exception:
            logger.exception("Background session finalize failed for %s", session_id)

    asyncio.create_task(_run())

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
                SELECT DISTINCT s.id, s.started_at, s.model, s.title, s.agent_id 
                FROM sessions s
                JOIN messages m ON s.id = m.session_id
                ORDER BY s.started_at DESC
            """
            async with conn.execute(query) as cursor:
                rows = await cursor.fetchall()
                
            # If no sessions have messages, return the most recent session
            if not rows:
                async with conn.execute("SELECT id, started_at, model, title, agent_id FROM sessions ORDER BY started_at DESC LIMIT 1") as cursor:
                    rows = await cursor.fetchall()
                    
            return [{
                "session_id": r["id"],
                "started_at": r["started_at"],
                "model": r["model"] or "house-party",
                "title": r["title"] or r["id"],
                "agent_id": r["agent_id"] or "jarvis"
            } for r in rows]
    except Exception as e:
        logger.exception("Failed to list sessions")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/sessions")
async def create_session(req: CreateSessionRequest = CreateSessionRequest()):
    await init_services()
    schedule_session_finalize(req.finalize_session_id)
    try:
        import random
        session_id = f"session_{int(asyncio.get_event_loop().time())}_{random.randint(1000, 9999)}"
        
        # We pre-compile system instructions to record in the sessions table
        profile = await memory.build_profile_prompt()
        soul_body = ""
        soul_file = get_skills_dir() / "jarvis_soul" / "SKILL.md"
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


@app.post("/v1/sessions/{session_id}/finalize")
async def finalize_session_endpoint(session_id: str):
    """Background-learn from a session (summary + facts). Idempotent."""
    await init_services()
    schedule_session_finalize(session_id)
    return {"status": "scheduled", "session_id": session_id}

def synthesize_title(message: str) -> str:
    import re
    # Strip any @filename mentions
    cleaned = re.sub(r'@[^\s]+', '', message).strip()
    # Collapse multiple whitespaces
    collapsed = " ".join(cleaned.split())
    if not collapsed:
        return "Untitled Session"
    if len(collapsed) <= 60:
        return collapsed
    return collapsed[:59] + "…"

async def run_agent_turn(session_id: str, prompt: str, exclude_client_id: Optional[str] = None, files: Optional[List[dict]] = None):
    """Executes the agent turn in a background task and streams updates."""
    async with _session_turn_lock(session_id):
        await _run_agent_turn_locked(
            session_id, prompt, exclude_client_id=exclude_client_id, files=files
        )


async def _run_agent_turn_locked(
    session_id: str,
    prompt: str,
    exclude_client_id: Optional[str] = None,
    files: Optional[List[dict]] = None,
):
    # Set the ContextVar for the current task so tool telemetry knows the session_id
    current_session_id.set(session_id)
    
    # Broadcast the user prompt to all other clients subscribed to the stream
    import time
    await broadcast_event(session_id, "user_message", {"text": prompt, "timestamp": time.time()}, exclude_client_id=exclude_client_id)
    
    try:
        # Resolve attachments and build full prompt
        full_prompt = prompt
        if files:
            attachment_segments = []
            for f in files:
                file_id = f.get("id")
                filename = f.get("filename")
                if file_id and filename:
                    file_path = get_data_dir() / "sessions" / session_id / "files" / file_id / filename
                    if file_path.exists():
                        try:
                            # Attempt to read as text
                            content = file_path.read_text(encoding="utf-8")
                            attachment_segments.append(f"[Attached File: {filename} ({file_path.stat().st_size} bytes)]\n{content}")
                        except Exception as file_err:
                            logger.warning(f"Could not read attachment {filename}: {file_err}")
            if attachment_segments:
                full_prompt = "\n\n".join(attachment_segments) + "\n\n" + prompt

        # 1. Add user message to SQLite memory
        await memory.add_message(session_id, "user", full_prompt)
        
        # 2. Compile instructions and active tools
        profile = await memory.build_profile_prompt()
        soul_body = ""
        soul_file = get_skills_dir() / "jarvis_soul" / "SKILL.md"
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
        voice_on = await _voice_mode_enabled()
        if voice_on:
            custom_instructions += f"\n\n{VOICE_MODE_SYSTEM_APPEND}"
        
        skills_tools = load_skills_from_dir(get_skills_dir())
        all_tools = [forge_skill] + skills_tools
        
        # Fetch session model and agent_id from SQLite
        session_model = "house-party"
        active_agent_id = "jarvis"
        try:
            import aiosqlite
            async with aiosqlite.connect(memory.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute("SELECT model, agent_id FROM sessions WHERE id = ?", (session_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        if row["model"]:
                            session_model = row["model"]
                        if row["agent_id"]:
                            active_agent_id = row["agent_id"]
        except Exception:
            logger.exception("Failed to fetch session model / agent_id")

        # 3. Run turn via Handoff workflow (default) or direct subagent override
        accumulated_text = ""

        if active_agent_id == "jarvis":
            accumulated_text = await run_handoff_turn(
                session_id,
                full_prompt,
                api_key=os.environ.get("NVIDIA_API_KEY", ""),
                jarvis_instructions=custom_instructions,
                session_model=session_model,
                memory=memory,
            )
        elif active_agent_id in ("friday", "homer", "plato"):
            subagent_dir = get_subagent_dir(active_agent_id)
            config_file = subagent_dir / "config.yaml"
            soul_file = subagent_dir / f"{active_agent_id}_soul.md"
            
            from jarvis.core.subagents import parse_simple_yaml
            from jarvis.core.soul import load_compiled_soul
            from agent_framework import Agent
            from jarvis.core.agent import StarkNIMChatClient
            
            config = parse_simple_yaml(config_file.read_text(encoding="utf-8"))
            _, instructions = load_compiled_soul(active_agent_id)
            if voice_on:
                instructions = f"{instructions}\n\n{VOICE_MODE_SYSTEM_APPEND}"
            
            model = config.get("model", "house-party")
            sub_tools = load_skills_from_dir(subagent_dir)

            api_key = os.environ.get("NVIDIA_API_KEY", "")
            client = StarkNIMChatClient(api_key=api_key)
            apply_primary_model(client, model)
            
            agent = Agent(
                client=client,
                name=active_agent_id.upper(),
                instructions=instructions,
                tools=sub_tools
            )
            apply_primary_model(agent.client, session_model)

            history_msgs = await memory.get_session_history(session_id)
            from agent_framework._types import Message
            agent_msgs = []
            for m in history_msgs:
                agent_msgs.append(Message(role=m["role"], contents=[m["content"] or ""]))
                
            raw_buffer = ""
            last_reasoning = ""
            last_text = ""
            
            async for chunk in agent.run(messages=agent_msgs, stream=True):
                if chunk.text:
                    raw_buffer += chunk.text
                    
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
                    
                    if current_reasoning != last_reasoning:
                        diff = current_reasoning[len(last_reasoning):]
                        await broadcast_event(session_id, "reasoning_chunk", {"text": diff})
                        last_reasoning = current_reasoning
                        
                    if current_text != last_text:
                        diff = current_text[len(last_text):]
                        await broadcast_event(session_id, "text_chunk", {"text": diff})
                        last_text = current_text
                        
            if last_reasoning:
                accumulated_text += f"<think>\n{last_reasoning}\n</think>\n"
            accumulated_text += last_text
        else:
            agent = create_jarvis_agent(
                api_key=os.environ.get("NVIDIA_API_KEY", ""),
                instructions_override=custom_instructions,
                tools=all_tools
            )
            apply_primary_model(agent.client, session_model)
            accumulated_text = await run_handoff_turn(
                session_id,
                full_prompt,
                api_key=os.environ.get("NVIDIA_API_KEY", ""),
                jarvis_instructions=custom_instructions,
                session_model=session_model,
                memory=memory,
            )
        
        if accumulated_text.strip():
            await memory.add_message(session_id, "assistant", accumulated_text)

        if await _voice_mode_enabled():
            spoken_text = clean_text_for_speech(accumulated_text)
            if spoken_text:
                await broadcast_event(
                    session_id,
                    "voice_ready",
                    {"text": spoken_text},
                )
            
        await broadcast_event(session_id, "turn_complete", {"session_id": session_id})
        logger.info(f"Session {session_id} turn completed successfully.")
        
    except Exception as e:
        logger.exception(f"Error executing agent turn for session {session_id}")
        # Drop poisoned MAF workflow state so the next turn is not blocked by
        # leftover in-flight executor messages from a mid-run failure.
        clear_workflow_state(session_id)
        await broadcast_event(session_id, "text_chunk", {"text": f"\n\n[bold red]System Error:[/] {e}\n"})
        await broadcast_event(session_id, "turn_complete", {"session_id": session_id})

@app.post("/v1/sessions/{session_id}/chat")
async def post_message(session_id: str, req: ChatRequest):
    await init_services()
    
    # Dynamic title generation on first message
    try:
        import aiosqlite
        async with aiosqlite.connect(memory.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT title FROM sessions WHERE id = ?", (session_id,)) as cursor:
                row = await cursor.fetchone()
                if row and not row["title"]:
                    title = synthesize_title(req.message)
                    await memory.update_session_title(session_id, title)
    except Exception:
        logger.exception("Failed to auto-generate session title")

    # Start task in background to process and stream via SSE
    asyncio.create_task(run_agent_turn(session_id, req.message, exclude_client_id=req.client_id, files=req.files))
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
            async with conn.execute("SELECT id, model, started_at, title, agent_id FROM sessions WHERE id = ?", (session_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "session_id": row["id"],
                        "model": row["model"] or "house-party",
                        "started_at": row["started_at"],
                        "title": row["title"] or row["id"],
                        "agent_id": row["agent_id"] or "jarvis"
                    }
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
    return {"models": ["house-party"] + NIM_MODEL_BASKET}

class ModelUpdateRequest(BaseModel):
    model: str

@app.post("/v1/sessions/{session_id}/model")
async def update_session_model(session_id: str, req: ModelUpdateRequest):
    await init_services()
    normalized_model = normalize_session_model(req.model)
    if not is_house_party(normalized_model) and normalized_model not in NIM_MODEL_BASKET:
        raise HTTPException(status_code=400, detail=f"Unknown model: {req.model}")
    try:
        import aiosqlite
        async with aiosqlite.connect(memory.db_path) as conn:
            await conn.execute(
                "UPDATE sessions SET model = ? WHERE id = ?",
                (normalized_model, session_id),
            )
            await conn.commit()
        clear_workflow_state(session_id)
        logger.info(f"Updated session {session_id} model to {normalized_model}")
        return {"status": "success", "model": normalized_model}
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
        from jarvis.core.soul import load_compiled_soul
        from jarvis.skills.skill_forge import load_skills_from_dir
        
        subagent_dir = get_subagent_dir(name_clean)
        config_file = subagent_dir / "config.yaml"
        soul_file = subagent_dir / f"{name_clean}_soul.md"
        
        if not config_file.exists() or not soul_file.exists():
            raise HTTPException(status_code=404, detail="Subagent configuration missing")
            
        config = parse_simple_yaml(config_file.read_text(encoding="utf-8"))
        doc, instructions = load_compiled_soul(name_clean)

        model = normalize_session_model(config.get("model", "house-party"))
        tools_list = load_skills_from_dir(subagent_dir)
        tools = [{"name": t.name, "description": t.description} for t in tools_list]

        fm = doc.frontmatter
        meta = {
            "role": fm.get("role"),
            "version": fm.get("version"),
            "output_contract": fm.get("output_contract"),
            "owns": fm.get("owns") if isinstance(fm.get("owns"), list) else [],
            "forbidden": fm.get("forbidden") if isinstance(fm.get("forbidden"), list) else [],
        }
        
        return {
            "name": name_clean.upper(),
            "model": model,
            "instructions": instructions,
            "tools": tools,
            "meta": meta,
        }
    except Exception as e:
        logger.exception(f"Failed to load subagent {name}")
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/v1/sessions/{session_id}/files")
async def upload_session_file(session_id: str, file: UploadFile = File(...)):
    await init_services()
    try:
        import uuid
        file_id = f"file_{uuid.uuid4().hex[:12]}"
        filename = file.filename or "file"
        
        # Save file to data/sessions/{session_id}/files/{file_id}/{filename}
        file_dir = get_data_dir() / "sessions" / session_id / "files" / file_id
        file_dir.mkdir(parents=True, exist_ok=True)
        file_path = file_dir / filename
        
        contents = await file.read()
        file_path.write_bytes(contents)
        
        return {
            "id": file_id,
            "filename": filename,
            "bytes": len(contents)
        }
    except Exception as e:
        logger.exception("Failed to upload session file")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/sessions/{session_id}/files/{file_id}/content")
async def get_session_file_content(session_id: str, file_id: str):
    await init_services()
    try:
        file_dir = get_data_dir() / "sessions" / session_id / "files" / file_id
        if not file_dir.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        # Find the first file in the directory
        files = list(file_dir.glob("*"))
        if not files:
            raise HTTPException(status_code=404, detail="File not found")
        
        file_path = files[0]
        return FileResponse(path=str(file_path), filename=file_path.name)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get session file content")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/captures/{filename}")
async def get_capture(filename: str):
    await init_services()
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid capture filename")
    file_path = get_webvision_dir() / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Capture not found")
    return FileResponse(path=str(file_path), filename=file_path.name)


@app.post("/v1/sessions/{session_id}/approve")
async def approve_tool_action(session_id: str, req: ApprovalRequest):
    await init_services()
    accepted = await submit_approval(session_id, req.request_id, req.approved)
    if not accepted:
        raise HTTPException(status_code=404, detail="No pending approval for this session")
    await broadcast_event(
        session_id,
        "approval_resolved",
        {"request_id": req.request_id, "approved": req.approved},
    )
    return {"status": "accepted", "approved": req.approved}


@app.post("/v1/sessions/{session_id}/switch-agent")
async def switch_session_agent(session_id: str, req: AgentSwitchRequest):
    await init_services()
    try:
        agent_id = req.agent_id.lower().strip()
        if agent_id not in ("jarvis", "friday", "homer", "plato"):
            raise HTTPException(status_code=400, detail=f"Invalid agent ID: {agent_id}")
            
        await memory.update_session_agent(session_id, agent_id)
        if agent_id != "jarvis":
            clear_workflow_state(session_id)
        
        # Broadcast the agent switch to all listeners so clients update their UI
        await broadcast_event(session_id, "agent_changed", {"agent_id": agent_id})
        
        return {"status": "success", "agent_id": agent_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to switch session agent")
        raise HTTPException(status_code=500, detail=str(e))

async def _voice_mode_enabled() -> bool:
    prefs = await memory.get_preferences()
    value = prefs.get(VOICE_MODE_PREF_KEY, False)
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    return bool(value)

@app.get("/v1/voice/status")
async def get_voice_status():
    await init_services()
    client = get_speech_client()
    enabled = await _voice_mode_enabled()
    voice = None
    language = None
    gender = None
    warning = None
    if client.tts_available:
        try:
            voice = client.ensure_voice()
            language = "en-US"
            gender = client.voice_gender()
            warning = client.persona_mismatch_warning()
        except Exception as exc:
            logger.warning("Voice status resolution failed: %s", exc)
    api_key_error = nvidia_api_key_problem()
    return {
        "enabled": enabled,
        "voice": voice,
        "language": language,
        "gender": gender,
        "persona_warning": warning,
        "tts_available": client.tts_available,
        "stt_available": client.stt_available,
        "error": client.init_error or api_key_error,
        "api_key_configured": api_key_error is None,
    }

@app.post("/v1/voice/mode")
async def set_voice_mode(req: VoiceModeRequest):
    await init_services()
    await memory.upsert_preference(VOICE_MODE_PREF_KEY, req.enabled)
    client = get_speech_client()
    if req.enabled and not client.is_available:
        detail = client.init_error or "NVIDIA NIM speech services unavailable"
        if "riva" in detail.lower():
            detail = f"{detail}. Run ./run.sh to install speech dependencies."
        raise HTTPException(status_code=503, detail=detail)
    return {"enabled": req.enabled}

@app.post("/v1/voice/tts")
async def synthesize_voice(req: VoiceTTSRequest):
    await init_services()
    client = get_speech_client()
    if not client.tts_available:
        raise HTTPException(
            status_code=503,
            detail=client.init_error or "TTS service unavailable",
        )
    try:
        wav_bytes = client.synthesize(req.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("TTS synthesis failed")
        raise HTTPException(
            status_code=502,
            detail=format_nvidia_speech_error(exc),
        ) from exc

    from fastapi.responses import Response
    return Response(content=wav_bytes, media_type="audio/wav")

@app.post("/v1/voice/stt")
async def transcribe_voice(audio: UploadFile = File(...)):
    await init_services()
    client = get_speech_client()
    if not client.stt_available:
        raise HTTPException(
            status_code=503,
            detail=client.init_error or "STT service unavailable",
        )
    try:
        audio_bytes = await audio.read()
        result = client.transcribe(audio_bytes, audio.content_type)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("STT transcription failed")
        raise HTTPException(
            status_code=502,
            detail=format_nvidia_speech_error(exc),
        ) from exc
    return result

def import_json_str(data: dict) -> str:
    import json
    return json.dumps(data)

# Serve built React Web UI at "/"
web_ui_dist = get_web_dist_dir()
if web_ui_dist.is_dir() and (web_ui_dist / "index.html").is_file():
    app.mount("/", StaticFiles(directory=str(web_ui_dist), html=True), name="web-ui")
