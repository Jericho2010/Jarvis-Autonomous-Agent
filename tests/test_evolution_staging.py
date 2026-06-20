import pytest
from pathlib import Path

from evolution.subconscious import staging
from evolution.subconscious.forge_pipeline import parse_forge_response, validate_forge_proposal


@pytest.fixture
def evo_paths(tmp_path, monkeypatch):
    staging_root = tmp_path / "skills_staging"
    skills_dir = tmp_path / "skills"
    manifest = tmp_path / "data" / "evolution_manifest.json"
    for sub in ("pray", "dream", "rejected"):
        (staging_root / sub).mkdir(parents=True)
    skills_dir.mkdir()
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"skills": {}}', encoding="utf-8")

    monkeypatch.setattr(staging, "get_staging_dir", lambda: staging_root)
    monkeypatch.setattr(staging, "get_skills_dir", lambda: skills_dir)
    monkeypatch.setattr(staging, "get_evolution_manifest_path", lambda: manifest)
    return {"staging": staging_root, "skills": skills_dir, "manifest": manifest}


SAMPLE_CODE = '''
from agent_framework import tool

@tool(approval_mode="never_require")
def hello_staged() -> str:
    return "hello"
'''


def test_resolve_unique_name_when_live_exists(evo_paths):
    live = evo_paths["skills"] / "ping_tool.py"
    live.write_text("# live", encoding="utf-8")
    final, original = staging.resolve_unique_name("ping_tool")
    assert final != "ping_tool"
    assert original == "ping_tool"


def test_register_and_list_pending(evo_paths):
    pray_dir = evo_paths["staging"] / "pray"
    (pray_dir / "demo_skill.py").write_text(SAMPLE_CODE, encoding="utf-8")
    staging.register_staged_skill(
        name="demo_skill",
        source="pray",
        summary="A demo",
        test_command="true",
        test_passed=True,
        evolution_log="data/evolution_logs/test-pray.md",
    )
    pending = staging.list_pending()
    assert len(pending) == 1
    assert pending[0]["name"] == "demo_skill"


def test_approve_promotes_to_live(evo_paths):
    pray_dir = evo_paths["staging"] / "pray"
    (pray_dir / "demo_skill.py").write_text(SAMPLE_CODE, encoding="utf-8")
    staging.register_staged_skill(
        name="demo_skill",
        source="pray",
        summary="A demo",
        test_command="true",
        test_passed=True,
        evolution_log="log.md",
    )
    ok, msg = staging.approve_skill("demo_skill")
    assert ok, msg
    assert (evo_paths["skills"] / "demo_skill.py").exists()
    assert not (pray_dir / "demo_skill.py").exists()
    manifest = staging.load_manifest()
    assert manifest["skills"]["demo_skill"]["status"] == "approved"


def test_approve_blocked_when_live_exists(evo_paths):
    pray_dir = evo_paths["staging"] / "pray"
    (pray_dir / "demo_skill.py").write_text(SAMPLE_CODE, encoding="utf-8")
    (evo_paths["skills"] / "demo_skill.py").write_text("# existing", encoding="utf-8")
    staging.register_staged_skill(
        name="demo_skill",
        source="pray",
        summary="A demo",
        test_command="true",
        test_passed=True,
        evolution_log="log.md",
    )
    ok, msg = staging.approve_skill("demo_skill")
    assert not ok
    assert "already exists" in msg


def test_reject_moves_to_archaeology(evo_paths):
    pray_dir = evo_paths["staging"] / "pray"
    (pray_dir / "demo_skill.py").write_text(SAMPLE_CODE, encoding="utf-8")
    staging.register_staged_skill(
        name="demo_skill",
        source="dream",
        summary="Rejected demo",
        test_command="true",
        test_passed=True,
        evolution_log="log.md",
    )
    ok, msg = staging.reject_skill("demo_skill")
    assert ok, msg
    assert (evo_paths["staging"] / "rejected" / "demo_skill.py").exists()
    rejected = staging.list_rejected()
    assert len(rejected) == 1


def test_dream_dedup_same_night_pray(evo_paths, monkeypatch):
    staging.register_staged_skill(
        name="shared_tool",
        source="pray",
        summary="Ping hosts for latency",
        test_command="true",
        test_passed=True,
        evolution_log="log.md",
    )
    (evo_paths["staging"] / "pray" / "shared_tool.py").write_text(SAMPLE_CODE, encoding="utf-8")
    assert staging.is_dream_duplicate_of_pray("shared_tool", "Ping hosts for latency check")


def test_parse_forge_response_json():
    raw = '{"forge": false, "reason": "quiet night"}'
    data = parse_forge_response(raw)
    assert data["forge"] is False


def test_validate_forge_proposal_requires_fields():
    assert validate_forge_proposal({"forge": True, "skill_name": "x"}) is not None
    assert validate_forge_proposal({"forge": False}) is None
