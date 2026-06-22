"""MAF HandoffBuilder workflow for Jarvis / Homer / Friday / Plato digital hands."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from agent_framework import Agent, AgentResponseUpdate, Content, MCPStdioTool, Workflow
from agent_framework._workflows._events import WorkflowEvent
from agent_framework.orchestrations import HandoffAgentUserRequest, HandoffBuilder, HandoffSentEvent

from jarvis.config.models import SUBAGENT_MODEL_BASKET, apply_primary_model
from jarvis.config.paths import get_skills_dir, get_subagent_dir
from jarvis.core.agent import DEFAULT_SYSTEM_PROMPT, StarkNIMChatClient
from jarvis.core.playwright_mcp import get_playwright_mcp_manager
from jarvis.core.simple_yaml import parse_simple_yaml
from jarvis.core.soul import load_compiled_soul
from jarvis.core.subagents import broadcast_event
from jarvis.memory.memory_manager import MemoryManager
from jarvis.skills.skill_forge import forge_skill, load_skills_from_dir

logger = logging.getLogger("jarvis.handoff_workflow")

_SPECIALIST_AGENT_IDS = frozenset({"homer", "friday", "plato"})
_SPECIALIST_CONTINUE = (
    "Continue the delegated task autonomously. Use your tools. Hand back to Jarvis when complete."
)
_MAX_HANDOFF_USER_REQUEST_ITERATIONS = 20

HANDOFF_TRIAGE_INSTRUCTIONS = """
# DIGITAL HANDS DELEGATION
You coordinate specialist agents via handoff tools — do not attempt browser or desktop automation yourself.

Route to **Homer** when:
- The question needs **current web data** you cannot confidently answer from memory
- Live pages, forms, browser screenshots, or multi-source verification with citations
- Official docs, changelogs, pricing, news, or comparisons beyond a quick reply

Homer handoff MUST include: the question, any known URLs, depth (quick vs deep).

Route to **Friday** when:
- Desktop screenshot (Retinal HUD) is needed — capture-only or before kinetic work
- Native app interaction: click, type, scroll, window focus (not browser)
- The task cannot be done via bash/file tools alone
- User asks what video, app, or website is currently on screen (desktop recon)

Friday handoff MUST include: target app/window, desired end state, kinetic authorization, destructive-action flag if applicable.

Route to **Homer** for follow-up summarisation when:
- User asks to summarise a video or page already identified in this session
- Pass Homer the **exact title, browser/app, and any YouTube URL** from Friday's prior report in the same session

Homer handoff for video summary MUST include: video title, platform/browser, URL if known, and genre or depth if the user specified it.

When the user asks to summarise a video after Friday recon in the same session:
- If Friday reported active_window is NOT media but listed a media candidate (e.g. YouTube in Firefox), hand off to Homer for THAT candidate only.
- Homer handoff MUST include: exact title, browser, note that it is a background tab (not the active window), user genre hint (e.g. comedy), and any URL if known.
- Do NOT substitute a different tab than Friday's media candidate.
- If user genre conflicts with the title (e.g. comedy vs rugby announcement), Homer should note the mismatch in the summary.

Route to **Plato** when:
- `forge_skill` fails or a skill in `skills/` / `skills_staging/` needs audit
- `execute_bash` or `read_file_content` / `write_file_content` fails and root-cause is unclear
- Code review, architecture critique, or technical decomposition is needed

Plato handoff MUST include: tool name, full error output, file paths, what you already tried.

Handle greetings, opinions, and general conversation directly in character. Only hand off when specialist work is required.

Use `recall_past_chats` when Shaun references earlier sessions, past decisions, or asks what was discussed before.

# AFTER SPECIALIST RETURNS
1. Preserve evidence — do not strip URLs, capture paths, file:line citations, or confidence levels.
2. Summarize for Shaun in your butler voice; specialist output is source of truth.
3. Act on next steps when safe:
   - Homer "Next steps for Jarvis" → delegate or answer locally
   - Friday "Blockers" → explain approval/desktop guard; retry if appropriate
   - Plato "Recommendations for Jarvis" → attempt top recommendation via forge_skill/bash/file ops
4. Do not re-do specialist work unless it failed.
"""


def _compiled_soul_instructions(name: str, fallback: str) -> str:
    try:
        _, compiled = load_compiled_soul(name)
        return compiled or fallback
    except FileNotFoundError:
        return fallback


def _homer_tools(mcp_tool: Optional[MCPStdioTool]) -> list[Any]:
    homer_dir = get_subagent_dir("homer")
    tools = load_skills_from_dir(homer_dir)
    if mcp_tool is not None:
        tools = tools + [mcp_tool]
    return tools


def _friday_tools() -> list[Any]:
    return load_skills_from_dir(get_subagent_dir("friday"))


def _plato_tools() -> list[Any]:
    return load_skills_from_dir(get_subagent_dir("plato"))


def _jarvis_tools() -> list[Any]:
    root_skills = load_skills_from_dir(get_skills_dir())
    return [forge_skill] + root_skills


def build_handoff_workflow(
    *,
    api_key: str,
    jarvis_instructions: str,
    session_model: str,
    homer_model: str,
    friday_model: str,
    plato_model: str,
    mcp_tool: Optional[MCPStdioTool],
) -> Workflow:
    jarvis_client = StarkNIMChatClient(api_key=api_key)
    homer_client = StarkNIMChatClient(api_key=api_key, model_basket=SUBAGENT_MODEL_BASKET)
    friday_client = StarkNIMChatClient(api_key=api_key, model_basket=SUBAGENT_MODEL_BASKET)
    plato_client = StarkNIMChatClient(api_key=api_key, model_basket=SUBAGENT_MODEL_BASKET)

    apply_primary_model(jarvis_client, session_model)
    apply_primary_model(homer_client, homer_model)
    apply_primary_model(friday_client, friday_model)
    apply_primary_model(plato_client, plato_model)

    jarvis = Agent(
        id="jarvis",
        name="jarvis",
        client=jarvis_client,
        instructions=jarvis_instructions,
        tools=_jarvis_tools(),
        require_per_service_call_history_persistence=True,
    )

    homer_soul = _compiled_soul_instructions(
        "homer",
        "You are Homer, web research and browser automation specialist.",
    )
    homer = Agent(
        id="homer",
        name="homer",
        client=homer_client,
        instructions=homer_soul or "You are Homer, web research and browser automation specialist.",
        tools=_homer_tools(mcp_tool),
        require_per_service_call_history_persistence=True,
    )

    friday_soul = _compiled_soul_instructions(
        "friday",
        "You are Friday, desktop automation specialist.",
    )
    friday = Agent(
        id="friday",
        name="friday",
        client=friday_client,
        instructions=friday_soul or "You are Friday, desktop automation specialist.",
        tools=_friday_tools(),
        require_per_service_call_history_persistence=True,
    )

    plato_soul = _compiled_soul_instructions(
        "plato",
        "You are Plato, code analysis and strategy specialist.",
    )
    plato = Agent(
        id="plato",
        name="plato",
        client=plato_client,
        instructions=plato_soul or "You are Plato, code analysis and strategy specialist.",
        tools=_plato_tools(),
        require_per_service_call_history_persistence=True,
    )

    builder = HandoffBuilder(
        name="jarvis_digital_hands",
        participants=[jarvis, homer, friday, plato],
    )
    (
        builder.add_handoff(
            jarvis,
            [homer],
            description="Browser navigation, live web pages, or deep web research.",
        )
        .add_handoff(
            jarvis,
            [friday],
            description="Desktop clicks, typing, scrolling, window focus, or screen capture.",
        )
        .add_handoff(
            jarvis,
            [plato],
            description="Code review, static analysis, architecture critique, or technical drafting.",
        )
        .add_handoff(
            homer,
            [jarvis],
            description="Return to Jarvis after browser work is complete or needs triage.",
        )
        .add_handoff(
            friday,
            [jarvis],
            description="Return to Jarvis after desktop work is complete or needs triage.",
        )
        .add_handoff(
            plato,
            [jarvis],
            description="Return to Jarvis after analysis or drafting is complete or needs triage.",
        )
    )
    return (
        builder.with_start_agent(jarvis)
        .with_autonomous_mode(
            agents=[homer, friday, plato],
            turn_limits={
                "homer": 12,
                "friday": 8,
                "plato": 10,
            },
            prompts={
                "homer": (
                    "Complete the delegated web research autonomously. "
                    "Use tools. Hand back to Jarvis when done."
                ),
                "friday": (
                    "Complete the delegated desktop task autonomously. "
                    "Hand back to Jarvis when done."
                ),
                "plato": (
                    "Complete the delegated analysis autonomously. "
                    "Hand back to Jarvis when done."
                ),
            },
        )
        .build()
    )


def _handoff_response_for_request(source_executor_id: Optional[str]) -> list[Any]:
    """Return MAF continuation payload for a HandoffAgentUserRequest."""
    agent = (source_executor_id or "").lower()
    if agent in _SPECIALIST_AGENT_IDS:
        return HandoffAgentUserRequest.create_response(_SPECIALIST_CONTINUE)
    return HandoffAgentUserRequest.terminate()


def compile_jarvis_instructions(custom_instructions: str) -> str:
    return f"{custom_instructions}\n\n{HANDOFF_TRIAGE_INSTRUCTIONS}"


def resolve_subagent_model(name: str, fallback: str) -> str:
    config_file = get_subagent_dir(name) / "config.yaml"
    if not config_file.exists():
        return fallback
    config = parse_simple_yaml(config_file.read_text(encoding="utf-8"))
    return config.get("model", fallback)


@dataclass
class SessionWorkflowState:
    workflow: Workflow
    session_model: str
    rehydrated: bool = False
    approval_event: asyncio.Event = field(default_factory=asyncio.Event)
    pending_approval: Optional[WorkflowEvent] = None
    approval_result: Optional[Any] = None
    turn_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_session_states: Dict[str, SessionWorkflowState] = {}


async def get_or_create_workflow_state(
    session_id: str,
    *,
    api_key: str,
    jarvis_instructions: str,
    session_model: str,
    memory: Optional[MemoryManager] = None,
) -> SessionWorkflowState:
    existing = _session_states.get(session_id)
    if existing is not None and existing.session_model == session_model:
        return existing

    instructions = jarvis_instructions
    if memory is not None:
        block = await memory.format_rehydration_block(session_id)
        if block:
            instructions = f"{instructions}\n\n{block}"

    mcp_tool: Optional[MCPStdioTool] = None
    manager = get_playwright_mcp_manager()
    ok, detail = manager.node_version_ok()
    if ok:
        try:
            mcp_tool = await manager.start()
        except Exception as exc:
            logger.warning("Playwright MCP unavailable for handoff workflow: %s", exc)
    else:
        logger.warning("Skipping Playwright MCP: %s", detail)

    workflow = build_handoff_workflow(
        api_key=api_key,
        jarvis_instructions=compile_jarvis_instructions(instructions),
        session_model=session_model,
        homer_model=resolve_subagent_model("homer", session_model),
        friday_model=resolve_subagent_model("friday", session_model),
        plato_model=resolve_subagent_model("plato", session_model),
        mcp_tool=mcp_tool,
    )
    state = SessionWorkflowState(
        workflow=workflow,
        session_model=session_model,
        rehydrated=bool(memory),
    )
    _session_states[session_id] = state
    return state


def clear_workflow_state(session_id: str) -> None:
    _session_states.pop(session_id, None)


def get_pending_approval(session_id: str) -> Optional[Dict[str, Any]]:
    state = _session_states.get(session_id)
    if state is None or state.pending_approval is None:
        return None
    event = state.pending_approval
    data = event.data
    payload: Dict[str, Any] = {
        "request_id": event.request_id,
        "approved": None,
    }
    if isinstance(data, Content) and data.type == "function_approval_request":
        payload["function_name"] = data.name
        payload["arguments"] = data.arguments
    return payload


async def submit_approval(session_id: str, request_id: str, approved: bool) -> bool:
    state = _session_states.get(session_id)
    if state is None or state.pending_approval is None:
        return False
    if state.pending_approval.request_id != request_id:
        return False
    data = state.pending_approval.data
    if not isinstance(data, Content) or data.type != "function_approval_request":
        return False
    state.approval_result = data.to_function_approval_response(approved=approved)
    state.approval_event.set()
    return True


async def _process_workflow_event(session_id: str, event: WorkflowEvent) -> str:
    emitted = ""
    if event.type == "output" and isinstance(event.data, AgentResponseUpdate):
        text = event.data.text or ""
        if text:
            emitted += text
            await broadcast_event(session_id, "text_chunk", {"text": text})
        if event.executor_id:
            await broadcast_event(
                session_id,
                "handoff",
                {"agent": event.executor_id, "active": True},
            )
    elif event.type == "handoff_sent" and isinstance(event.data, HandoffSentEvent):
        await broadcast_event(
            session_id,
            "handoff",
            {"agent": event.data.target, "source": event.data.source},
        )
        await broadcast_event(session_id, "agent_changed", {"agent_id": event.data.target})
    return emitted


async def _wait_for_approval(session_id: str, state: SessionWorkflowState) -> Dict[str, Any]:
    await broadcast_event(
        session_id,
        "approval_required",
        get_pending_approval(session_id) or {},
    )
    await broadcast_event(
        session_id,
        "text_chunk",
        {
            "text": (
                "\n\n[bold #FFD700]Desktop action pending approval — "
                "approve or reject in the Web HUD.[/]\n"
            )
        },
    )
    state.approval_event.clear()
    await state.approval_event.wait()
    response = state.approval_result
    request_id = state.pending_approval.request_id if state.pending_approval else ""
    state.pending_approval = None
    state.approval_result = None
    return {request_id: response}


async def _drain_workflow_run(
    session_id: str,
    state: SessionWorkflowState,
    *,
    message: Optional[str] = None,
    responses: Optional[Dict[str, Any]] = None,
) -> tuple[list[WorkflowEvent], str]:
    pending_user_requests: list[WorkflowEvent] = []
    collected: list[WorkflowEvent] = []
    accumulated_text = ""

    if message is not None:
        stream = state.workflow.run(message, stream=True)
    elif responses is not None:
        stream = state.workflow.run(stream=True, responses=responses)
    else:
        return collected, accumulated_text

    async for event in stream:
        collected.append(event)
        accumulated_text += await _process_workflow_event(session_id, event)

        if event.type == "request_info":
            if isinstance(event.data, Content) and event.data.type == "function_approval_request":
                state.pending_approval = event
                approval_responses = await _wait_for_approval(session_id, state)
                nested, nested_text = await _drain_workflow_run(
                    session_id,
                    state,
                    responses=approval_responses,
                )
                collected.extend(nested)
                accumulated_text += nested_text
                return collected, accumulated_text
            if isinstance(event.data, HandoffAgentUserRequest):
                pending_user_requests.append(event)

    iterations = 0
    while pending_user_requests and iterations < _MAX_HANDOFF_USER_REQUEST_ITERATIONS:
        iterations += 1
        batch = pending_user_requests
        pending_user_requests = []
        response_map = {
            req.request_id: _handoff_response_for_request(
                getattr(req, "source_executor_id", None)
            )
            for req in batch
        }
        nested, nested_text = await _drain_workflow_run(
            session_id,
            state,
            responses=response_map,
        )
        collected.extend(nested)
        accumulated_text += nested_text

    return collected, accumulated_text


async def run_handoff_turn(
    session_id: str,
    user_message: str,
    *,
    api_key: str,
    jarvis_instructions: str,
    session_model: str,
    memory: Optional[MemoryManager] = None,
) -> str:
    state = await get_or_create_workflow_state(
        session_id,
        api_key=api_key,
        jarvis_instructions=jarvis_instructions,
        session_model=session_model,
        memory=memory,
    )
    async with state.turn_lock:
        _, accumulated_text = await _drain_workflow_run(session_id, state, message=user_message)
        await broadcast_event(session_id, "agent_changed", {"agent_id": "jarvis"})
        return accumulated_text
