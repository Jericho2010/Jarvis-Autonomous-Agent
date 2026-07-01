"""Startup dependency checks for desktop tools and Playwright MCP."""

from __future__ import annotations

import logging
import os
import shutil
from typing import TYPE_CHECKING, List, Optional

from jarvis.core.playwright_mcp import get_playwright_mcp_manager

if TYPE_CHECKING:
    from rich.console import Console

logger = logging.getLogger("jarvis.system_deps")

_DESKTOP_COMMANDS = ("xdotool", "scrot", "wmctrl")


def is_headless_environment() -> bool:
    """True in GitHub Codespaces or when no X11 display is available."""
    if os.environ.get("GITHUB_CODESPACES", "").lower() == "true":
        return True
    return not os.environ.get("DISPLAY")


def _missing_desktop_commands() -> List[str]:
    missing: List[str] = []
    for cmd in _DESKTOP_COMMANDS:
        if not shutil.which(cmd):
            missing.append(cmd)
    return missing


def _missing_node_dependency() -> Optional[str]:
    node_ok, node_detail = get_playwright_mcp_manager().node_version_ok()
    if not node_ok:
        return f"node ({node_detail})"
    return None


def check_system_dependencies(console: Optional["Console"] = None) -> None:
    """Log and optionally print missing system dependencies. Never raises."""
    missing: List[str] = []
    headless = is_headless_environment()

    if not headless:
        missing.extend(_missing_desktop_commands())

    node_missing = _missing_node_dependency()
    if node_missing:
        missing.append(node_missing)

    if not missing:
        return

    if console is not None:
        console.print(
            f"\n[bold #FFD700]⚠ Stark System Diagnostics // Missing dependencies: "
            f"{', '.join(missing)}[/bold #FFD700]"
        )
        if not headless and any(cmd in missing for cmd in _DESKTOP_COMMANDS):
            console.print(
                "[dim #FFD700]Desktop: sudo apt install scrot xdotool wmctrl[/]"
            )
        if node_missing:
            console.print(
                "[dim #FFD700]Browser MCP: Node 18+ and `npx playwright install`[/]\n"
            )
        elif not headless:
            console.print()

    logger.warning("Startup Diagnostics: Missing dependencies %s", missing)
