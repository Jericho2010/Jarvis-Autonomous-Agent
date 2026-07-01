from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from rich.errors import MarkupError

from jarvis.core.system_deps import (
    check_system_dependencies,
    is_headless_environment,
)


def test_is_headless_environment_codespaces():
    with patch.dict("os.environ", {"GITHUB_CODESPACES": "true", "DISPLAY": ":0"}, clear=False):
        assert is_headless_environment() is True


def test_is_headless_environment_no_display():
    with patch.dict("os.environ", {}, clear=True):
        assert is_headless_environment() is True


def test_is_headless_environment_desktop():
    with patch.dict("os.environ", {"DISPLAY": ":0"}, clear=True):
        assert is_headless_environment() is False


def test_headless_skips_desktop_command_checks():
    manager = MagicMock()
    manager.node_version_ok.return_value = (True, "v24.0.0")

    with patch.dict("os.environ", {"GITHUB_CODESPACES": "true"}, clear=False):
        with patch("jarvis.core.system_deps.shutil.which", return_value=None):
            with patch(
                "jarvis.core.system_deps.get_playwright_mcp_manager",
                return_value=manager,
            ):
                console = Console(record=True)
                check_system_dependencies(console)

    assert "xdotool" not in console.export_text()
    assert "scrot" not in console.export_text()
    assert "wmctrl" not in console.export_text()


def test_headless_still_checks_node():
    manager = MagicMock()
    manager.node_version_ok.return_value = (False, "node not found on PATH")

    with patch.dict("os.environ", {"GITHUB_CODESPACES": "true"}, clear=False):
        with patch(
            "jarvis.core.system_deps.get_playwright_mcp_manager",
            return_value=manager,
        ):
            console = Console(record=True)
            check_system_dependencies(console)

    output = console.export_text()
    assert "node" in output
    assert "playwright install" in output.lower()


def test_desktop_missing_commands_do_not_raise_markup_error():
    manager = MagicMock()
    manager.node_version_ok.return_value = (True, "v24.0.0")

    with patch.dict("os.environ", {"DISPLAY": ":0"}, clear=True):
        with patch("jarvis.core.system_deps.shutil.which", return_value=None):
            with patch(
                "jarvis.core.system_deps.get_playwright_mcp_manager",
                return_value=manager,
            ):
                console = Console(record=True)
                check_system_dependencies(console)

    output = console.export_text()
    assert "xdotool" in output
    assert "scrot" in output
    assert "wmctrl" in output
    assert "sudo apt install" in output


def test_invalid_rich_markup_would_raise():
    console = Console(record=True)
    with pytest.raises(MarkupError):
        console.print("[dim #FFD700]bad markup[/dim]")
