import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent_framework.orchestrations import HandoffAgentUserRequest

from jarvis.core.agent import ToolTelemetryMiddleware
from jarvis.core.handoff_workflow import (
    _handoff_response_for_request,
    compile_jarvis_instructions,
    submit_approval,
)
from jarvis.core.playwright_mcp import PlaywrightMCPManager


def test_handoff_response_for_specialist_uses_create_response():
    response = _handoff_response_for_request("homer")
    assert response != HandoffAgentUserRequest.terminate()
    assert len(response) == 1
    assert response[0].role == "user"


def test_handoff_response_for_jarvis_uses_terminate():
    assert _handoff_response_for_request("jarvis") == HandoffAgentUserRequest.terminate()
    assert _handoff_response_for_request(None) == HandoffAgentUserRequest.terminate()


def test_compile_jarvis_instructions_includes_delegation():
    text = compile_jarvis_instructions("Base prompt")
    assert "DIGITAL HANDS DELEGATION" in text
    assert "Homer" in text
    assert "Friday" in text
    assert "Plato" in text
    assert "forge_skill" in text
    assert "AFTER SPECIALIST RETURNS" in text
    assert "Recommendations for Jarvis" in text


def test_playwright_mcp_manager_node_version_ok():
    manager = PlaywrightMCPManager()
    with patch.object(manager, "node_available", return_value=True):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "v20.11.0\n"
            ok, detail = manager.node_version_ok()
    assert ok is True
    assert "v20" in detail


def test_playwright_mcp_create_tool_args():
    tool = PlaywrightMCPManager().create_tool()
    assert tool.name == "playwright_browser"
    assert tool.command == "npx"


@pytest.mark.asyncio
async def test_submit_approval_requires_pending_request():
    from jarvis.core import handoff_workflow as hw

    state = MagicMock()
    state.pending_approval = None
    hw._session_states["test-session"] = state
    try:
        assert await submit_approval("test-session", "req-1", True) is False
    finally:
        hw._session_states.pop("test-session", None)


@pytest.mark.asyncio
async def test_build_handoff_workflow_structure():
    from agent_framework import Workflow
    from jarvis.core.handoff_workflow import build_handoff_workflow

    with patch("jarvis.core.handoff_workflow.load_skills_from_dir", return_value=[]):
        with patch("jarvis.core.handoff_workflow.apply_primary_model"):
            workflow = build_handoff_workflow(
                api_key="test-key",
                jarvis_instructions="Jarvis test",
                session_model="house-party",
                homer_model="house-party",
                friday_model="house-party",
                plato_model="house-party",
                mcp_tool=None,
            )
    assert isinstance(workflow, Workflow)


def test_build_handoff_workflow_enables_autonomous_mode():
    from agent_framework.orchestrations import HandoffBuilder
    from jarvis.core.handoff_workflow import build_handoff_workflow

    with patch.object(
        HandoffBuilder,
        "with_autonomous_mode",
        wraps=HandoffBuilder.with_autonomous_mode,
    ) as mock_auto:
        with patch("jarvis.core.handoff_workflow.load_skills_from_dir", return_value=[]):
            with patch("jarvis.core.handoff_workflow.apply_primary_model"):
                build_handoff_workflow(
                    api_key="test-key",
                    jarvis_instructions="Jarvis test",
                    session_model="house-party",
                    homer_model="house-party",
                    friday_model="house-party",
                    plato_model="house-party",
                    mcp_tool=None,
                )

    mock_auto.assert_called_once()
    kwargs = mock_auto.call_args.kwargs
    assert kwargs["turn_limits"]["homer"] == 12
    assert kwargs["turn_limits"]["friday"] == 8
    assert kwargs["turn_limits"]["plato"] == 10
    agent_ids = {getattr(a, "id", a) for a in kwargs["agents"]}
    assert agent_ids == {"homer", "friday", "plato"}


@pytest.mark.asyncio
async def test_middleware_termination_emits_handoff_initiated_not_error():
    from agent_framework import MiddlewareTermination

    middleware = ToolTelemetryMiddleware()
    context = MagicMock()
    context.function.name = "handoff_to_homer"
    context.arguments = {}

    async def call_next():
        raise MiddlewareTermination(result={"handoff_to": "homer"})

    broadcast = AsyncMock()
    with patch("jarvis.core.subagents.current_session_id") as session_ctx:
        session_ctx.get.return_value = "sess-1"
        with patch("jarvis.core.subagents.broadcast_event", broadcast):
            with pytest.raises(MiddlewareTermination):
                await middleware.process(context, call_next)

    handoff_calls = [
        c for c in broadcast.call_args_list if c.args[1] == "handoff_initiated"
    ]
    assert handoff_calls
    assert handoff_calls[0].args[2]["target"] == "homer"

    error_completes = [
        c for c in broadcast.call_args_list
        if c.args[1] == "tool_call_complete" and "error" in c.args[2]
    ]
    assert not error_completes
