import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jarvis.core.handoff_workflow import compile_jarvis_instructions, submit_approval
from jarvis.core.playwright_mcp import PlaywrightMCPManager


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
