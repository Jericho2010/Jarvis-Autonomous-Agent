import pytest
from pathlib import Path
from jarvis.skills.skill_forge import forge_skill, extract_imports, is_module_available, load_skills_from_dir
from jarvis.config.paths import get_skills_dir, get_subagent_dir

def test_extract_imports():
    code = """
import numpy as np
from os import path
import sys, json
from collections import defaultdict
"""
    imports = extract_imports(code)
    assert "numpy" in imports
    assert "os" in imports
    assert "sys" in imports
    assert "json" in imports
    assert "collections" in imports
    assert len(imports) == 5

def test_forge_skill_with_existing_dependency(tmp_path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr("jarvis.skills.skill_forge.get_skills_dir", lambda: skills_dir)
    
    code = """
from agent_framework import tool
import numpy as np

@tool(approval_mode="never_require")
def test_np_skill(x: int) -> int:
    return int(np.square(x))
"""
    res = forge_skill("test_np_skill", code)
    assert "✓ Skill 'test_np_skill' forged successfully!" in res


def test_load_skills_from_dir_loads_friday_app_launcher():
    tools = load_skills_from_dir(get_subagent_dir("friday"))
    names = {t.name for t in tools}
    assert "stark_os_armor_list_apps" in names
    assert "stark_os_armor_launch_app" in names


def test_load_skills_from_dir_loads_text_associator():
    tools = load_skills_from_dir(get_skills_dir())
    names = {t.name for t in tools}
    assert "creative_associator" in names
