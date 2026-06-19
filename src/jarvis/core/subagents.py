import os
import re
import logging
import contextvars
from pathlib import Path
from typing import Dict, Any, List

from agent_framework import Agent, tool
from jarvis.config.models import apply_primary_model
from jarvis.config.paths import get_subagent_dir
from jarvis.core.agent import StarkNIMChatClient
from jarvis.skills.skill_forge import load_skills_from_dir

logger = logging.getLogger("jarvis.subagents")

# Global context var to track the active session ID for broadcasting events
current_session_id = contextvars.ContextVar("current_session_id", default=None)

# Simple YAML parser to avoid PyYAML dependency
def parse_simple_yaml(content: str) -> dict:
    result = {}
    current_section = result
    for line in content.splitlines():
        if not line.strip() or line.strip().startswith('#'):
            continue
        indent = len(line) - len(line.lstrip())
        line_content = line.strip()
        if ':' in line_content:
            parts = line_content.split(':', 1)
            key = parts[0].strip()
            val = parts[1].strip()
            if val.startswith(('"', "'")) and val.endswith(('"', "'")):
                val = val[1:-1]
            if val == '':
                new_dict = {}
                result[key] = new_dict
                current_section = new_dict
            else:
                if val.lower() == 'true':
                    val = True
                elif val.lower() == 'false':
                    val = False
                elif val.lower() == 'none':
                    val = None
                else:
                    try:
                        val = float(val) if '.' in val else int(val)
                    except ValueError:
                        pass
                if indent > 0:
                    current_section[key] = val
                else:
                    result[key] = val
                    current_section = result
    return result

def load_subagent(name: str) -> Agent:
    """
    Loads and compiles a stateless subagent instance dynamically from its skills directory.
    """
    name = name.lower().strip()
    subagent_dir = get_subagent_dir(name)
    if not subagent_dir.exists():
        raise FileNotFoundError(f"Subagent directory not found: {subagent_dir}")
        
    config_file = subagent_dir / "config.yaml"
    soul_file = subagent_dir / f"{name}_soul.md"
    
    if not config_file.exists():
        raise FileNotFoundError(f"Subagent config file not found: {config_file}")
    if not soul_file.exists():
        raise FileNotFoundError(f"Subagent soul file not found: {soul_file}")
        
    # Parse config and soul
    config = parse_simple_yaml(config_file.read_text(encoding="utf-8"))
    instructions = soul_file.read_text(encoding="utf-8").strip()
    
    model = config.get("model", "house-party")

    # Load tools dynamically from the subagent's directory
    tools = load_skills_from_dir(subagent_dir)

    # Instantiate client and set its primary model
    api_key = os.environ.get("NVIDIA_API_KEY", "")
    client = StarkNIMChatClient(api_key=api_key)
    apply_primary_model(client, model)
    
    # Compile Agent
    agent = Agent(
        client=client,
        name=name.upper(),
        instructions=instructions,
        tools=tools
    )
    return agent

# Broadcast queue registry (will be populated by FastAPI server)
# maps session_id -> list of asyncio.Queue instances
session_broadcasters: Dict[str, List[Any]] = {}

async def broadcast_event(session_id: str, event_type: str, data: dict, exclude_client_id: str = None):
    """Broadcasts an event to all active SSE queues for the session."""
    if not session_id or session_id not in session_broadcasters:
        return
    
    # Create copy to prevent concurrent modification during iteration
    subscribers = list(session_broadcasters[session_id])
    for sub in subscribers:
        if exclude_client_id and sub.get("client_id") == exclude_client_id:
            continue
        try:
            await sub["queue"].put({"event": event_type, "data": data})
        except Exception as e:
            logger.warning(f"Failed to put event into SSE queue: {e}")

@tool(approval_mode="never_require")
async def sys_session_send(subagent: str, prompt: str) -> str:
    """
    Delegate a sub-task to a specialized sub-agent (friday, homer, or plato) in an isolated session.
    
    Args:
        subagent: Name of the subagent ('friday', 'homer', or 'plato').
        prompt: Detailed instructions and context for the subagent to act upon.
        
    Returns:
        The response and results from the subagent.
    """
    subagent_name = subagent.lower().strip()
    if subagent_name not in ("friday", "homer", "plato"):
        return f"Error: Unknown subagent '{subagent}'. Choose from 'friday', 'homer', or 'plato'."
        
    # Get current session ID from context var
    session_id = current_session_id.get()
    
    await broadcast_event(
        session_id, 
        "text_chunk", 
        {"text": f"\n\n[bold #00F0FF]⬡ Orchestrator:[/] Delegating task to [bold #FFD700]{subagent_name.upper()}[/]...\n"}
    )
    
    try:
        # Load compiled subagent dynamically (picking up soul files changes immediately)
        agent = load_subagent(subagent_name)
        
        # Prepare stateless input
        from agent_framework._types import Message
        msgs = [Message(role="user", contents=[prompt])]
        
        # Run subagent in isolated session
        response_text = ""
        async for chunk in agent.run(messages=msgs, stream=True):
            if chunk.text:
                response_text += chunk.text
                # Broadcast subagent's generation to SSE stream in real-time
                await broadcast_event(session_id, "subagent_text_chunk", {"subagent": subagent_name, "text": chunk.text})
                
        return response_text
    except Exception as e:
        logger.exception(f"Subagent {subagent_name} run failed")
        err_msg = f"Error: Subagent delegation failed: {e}"
        await broadcast_event(session_id, "text_chunk", {"text": f"\n[bold red]{err_msg}[/]\n"})
        return err_msg
