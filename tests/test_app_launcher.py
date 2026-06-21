import json
from unittest.mock import MagicMock, patch

import pytest

from skills.friday import app_launcher as launcher


@pytest.fixture
def fake_apps_dir(tmp_path, monkeypatch):
    apps_dir = tmp_path / "applications"
    apps_dir.mkdir()
    (apps_dir / "notes.desktop").write_text(
        """[Desktop Entry]
Type=Application
Name=Notes
GenericName=Text Editor
Comment=Take notes
Exec=gnome-text-editor %U
Categories=Utility;
""",
        encoding="utf-8",
    )
    (apps_dir / "firefox.desktop").write_text(
        """[Desktop Entry]
Type=Application
Name=Firefox
Exec=firefox %u
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(launcher, "_desktop_search_dirs", lambda: [apps_dir])
    return apps_dir


def test_list_apps_filters_by_query(fake_apps_dir):
    result = json.loads(launcher.stark_os_armor_list_apps("notes"))
    assert result["success"] is True
    assert result["count"] == 1
    assert result["apps"][0]["desktop_id"] == "notes.desktop"
    assert result["apps"][0]["name"] == "Notes"


def test_list_apps_returns_multiple(fake_apps_dir):
    result = json.loads(launcher.stark_os_armor_list_apps(""))
    assert result["success"] is True
    assert result["count"] == 2


def test_launch_app_uses_gtk_launch(fake_apps_dir):
    class RunResult:
        returncode = 0
        stderr = ""
        stdout = ""

    def _which(cmd: str):
        return "/usr/bin/gtk-launch" if cmd == "gtk-launch" else None

    with patch.object(launcher.shutil, "which", side_effect=_which):
        with patch.object(launcher.subprocess, "run", return_value=RunResult()):
            result = json.loads(launcher.stark_os_armor_launch_app("notes"))
    assert result["success"] is True
    assert result["desktop_id"] == "notes.desktop"
    assert "gtk-launch notes" in result["method"]


def test_launch_app_no_match(fake_apps_dir):
    result = json.loads(launcher.stark_os_armor_launch_app("nonexistent-app-xyz"))
    assert result["success"] is False
    assert "No application matched" in result["error"]


def test_clean_exec_strips_field_codes():
    argv = launcher._clean_exec("firefox --new-window %u")
    assert argv == ["firefox", "--new-window"]
