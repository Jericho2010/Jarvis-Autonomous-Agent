import importlib.util
import json
import pytest
from pathlib import Path

_REPO_READER_PATH = Path(__file__).resolve().parents[1] / "skills" / "plato" / "repo_reader.py"
_spec = importlib.util.spec_from_file_location("repo_reader", _REPO_READER_PATH)
rr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rr)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.config.paths.get_workspace_root", lambda: tmp_path)
    monkeypatch.setattr(rr, "get_workspace_root", lambda: tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "hello.py").write_text("def greet():\n    return 'hi'\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Hello\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    return tmp_path


def test_read_repo_file_success(workspace):
    result = json.loads(rr.read_repo_file("src/hello.py"))
    assert result["success"] is True
    assert "def greet" in result["content"]
    assert result["total_lines"] == 2


def test_read_repo_file_rejects_escape(workspace):
    result = json.loads(rr.read_repo_file("../../etc/passwd"))
    assert result["success"] is False


def test_list_repo_files_skips_git(workspace):
    result = json.loads(rr.list_repo_files("."))
    assert result["success"] is True
    paths = result["files"]
    assert any("hello.py" in p for p in paths)
    assert not any(".git" in p for p in paths)


def test_grep_repo_files_finds_match(workspace):
    result = json.loads(rr.grep_repo_files("greet"))
    assert result["success"] is True
    assert result["count"] >= 1
    assert result["matches"][0]["path"].endswith("hello.py")


def test_grep_repo_files_invalid_regex(workspace):
    result = json.loads(rr.grep_repo_files("[invalid"))
    assert result["success"] is False
