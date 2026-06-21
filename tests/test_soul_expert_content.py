from pathlib import Path

import pytest

from jarvis.config.paths import get_subagent_dir
from jarvis.core.soul import load_compiled_soul

AGENTS = ("homer", "friday", "plato")

REQUIRED_MARKERS = {
    "homer": ("homer_intel_v1", "Deep research", "Browser automation", "Next steps for Jarvis"),
    "friday": ("friday_action_v1", "Retinal reconnaissance", "Kinetic task execution", "Next steps for Jarvis"),
    "plato": ("plato_review_v1", "Skill forge review", "Jarvis tool-failure diagnosis", "Recommendations for Jarvis"),
}


@pytest.mark.parametrize("agent", AGENTS)
def test_soul_files_have_expert_sections(agent):
    soul_path = get_subagent_dir(agent) / f"{agent}_soul.md"
    text = soul_path.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "# MUST" in text
    assert "# MUST NOT" in text
    for marker in REQUIRED_MARKERS[agent]:
        assert marker in text, f"{agent} missing {marker}"


@pytest.mark.parametrize("agent", AGENTS)
def test_compiled_souls_exclude_raw_frontmatter(agent):
    _, compiled = load_compiled_soul(agent)
    assert "agent_id:" not in compiled
    assert "# TEAM CONTRACT" in compiled
