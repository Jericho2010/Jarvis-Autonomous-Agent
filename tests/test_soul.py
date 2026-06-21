import pytest
from pathlib import Path

from jarvis.core.soul import (
    SoulDoc,
    compile_instructions,
    load_compiled_soul,
    parse_soul_file,
)


SAMPLE_SOUL = """---
name: TEST
agent_id: test
version: 1.0
role: Test agent
reports_to: jarvis
owns:
  - alpha capability
  - beta capability
forbidden:
  - bad behavior
tools:
  - tool_a
output_contract: test_v1
---

# Mission
You are a test agent.

# MUST
- Do things correctly.
"""


def test_parse_soul_file_frontmatter_and_body(tmp_path):
    path = tmp_path / "test_soul.md"
    path.write_text(SAMPLE_SOUL, encoding="utf-8")
    doc = parse_soul_file(path)
    assert doc.frontmatter["name"] == "TEST"
    assert doc.frontmatter["agent_id"] == "test"
    assert "alpha capability" in doc.frontmatter["owns"]
    assert "bad behavior" in doc.frontmatter["forbidden"]
    assert "tool_a" in doc.frontmatter["tools"]
    assert "# Mission" in doc.body
    assert "agent_id:" not in doc.body


def test_compile_instructions_appends_team_contract():
    doc = parse_soul_file(Path(__file__))  # will fail - use inline
    doc = SoulDoc(
        frontmatter={
            "reports_to": "jarvis",
            "owns": ["web research"],
            "forbidden": ["desktop automation"],
        },
        body="# Mission\nTest body.",
    )
    compiled = compile_instructions(doc)
    assert "Test body." in compiled
    assert "# TEAM CONTRACT" in compiled
    assert "web research" in compiled
    assert "desktop automation" in compiled
    assert "agent_id:" not in compiled


def test_compile_instructions_omits_contract_when_disabled():
    doc = SoulDoc(frontmatter={"owns": ["x"]}, body="Body only.")
    assert compile_instructions(doc, include_team_contract=False) == "Body only."


def test_load_compiled_soul_production_homer():
    doc, compiled = load_compiled_soul("homer")
    assert doc.frontmatter.get("output_contract") == "homer_intel_v1"
    assert "homer_intel_v1" in compiled
    assert "# MUST" in compiled
    assert "agent_id:" not in compiled


def test_load_compiled_soul_production_friday():
    _, compiled = load_compiled_soul("friday")
    assert "friday_action_v1" in compiled
    assert "Retinal reconnaissance" in compiled


def test_load_compiled_soul_production_plato():
    _, compiled = load_compiled_soul("plato")
    assert "plato_review_v1" in compiled
    assert "Skill forge review" in compiled
    assert "Recommendations for Jarvis" in compiled
