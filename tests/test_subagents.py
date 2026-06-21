import pytest
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from jarvis.core.subagents import parse_simple_yaml, load_subagent, sys_session_send

def test_parse_simple_yaml():
    yaml_content = """
    model: "nvidia/stepfun-ai/step-3.7-flash"
    options:
      temperature: 0.2
      max_tokens: 2048
    """
    data = parse_simple_yaml(yaml_content)
    assert data["model"] == "nvidia/stepfun-ai/step-3.7-flash"
    assert data["options"]["temperature"] == 0.2
    assert data["options"]["max_tokens"] == 2048

@pytest.mark.asyncio
async def test_sys_session_send_invalid_subagent():
    res = await sys_session_send("unknown_agent", "hello")
    assert "Error: Unknown subagent" in res

@pytest.mark.asyncio
async def test_load_and_run_subagent(tmp_path):
    subagent_dir = tmp_path / "skills" / "friday"
    subagent_dir.mkdir(parents=True)
    
    config_file = subagent_dir / "config.yaml"
    config_file.write_text("model: 'test-model'\noptions:\n  temperature: 0.1\n")
    
    soul_file = subagent_dir / "friday_soul.md"
    soul_file.write_text("""---
name: FRIDAY
agent_id: friday
version: 1.0
role: Test
reports_to: jarvis
owns:
  - testing
forbidden:
  - nothing
tools:
  - test_tool
output_contract: test_v1
---

You are F.R.I.D.A.Y. test agent.
""")
    
    # Mock StarkNIMChatClient and load_skills_from_dir
    with patch("jarvis.core.subagents.get_subagent_dir", return_value=tmp_path / "skills" / "friday"):
        with patch("jarvis.core.soul.get_subagent_dir", return_value=tmp_path / "skills" / "friday"):
            with patch("jarvis.core.subagents.load_skills_from_dir", return_value=[]):
                with patch("jarvis.core.subagents.StarkNIMChatClient") as mock_client_cls:
                    agent = load_subagent("friday")
                    assert agent.name == "FRIDAY"
                    assert "You are F.R.I.D.A.Y. test agent." in agent.default_options["instructions"]
                    assert "agent_id:" not in agent.default_options["instructions"]
                    assert "# TEAM CONTRACT" in agent.default_options["instructions"]
                    mock_client_cls.return_value.primary_model = "house_party"
