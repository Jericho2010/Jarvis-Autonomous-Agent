"""Desktop display environment detection for Friday kinetic tools."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("jarvis.display_env")


@dataclass(frozen=True)
class DisplayEnvironment:
    session_type: str
    display: Optional[str]
    x11_available: bool
    wayland_warning: Optional[str]
    xdotool_geometry: Optional[str]

    @property
    def desktop_automation_ready(self) -> bool:
        return self.x11_available

    def summary(self) -> str:
        parts = [f"session={self.session_type or 'unknown'}"]
        if self.display:
            parts.append(f"display={self.display}")
        if self.xdotool_geometry:
            parts.append(f"geometry={self.xdotool_geometry}")
        if self.wayland_warning:
            parts.append(f"warning={self.wayland_warning}")
        return "; ".join(parts)


def detect_display_environment() -> DisplayEnvironment:
    session_type = (os.environ.get("XDG_SESSION_TYPE") or "unknown").lower()
    display = os.environ.get("DISPLAY")
    wayland_warning: Optional[str] = None
    x11_available = False
    geometry: Optional[str] = None

    if session_type == "wayland":
        wayland_warning = (
            "Wayland session detected — xdotool/scrot/wmctrl require X11. "
            "Log into an X11 session or use XWayland for desktop automation."
        )
    elif not display:
        wayland_warning = "DISPLAY is unset — desktop automation tools will fail."

    if shutil.which("xdotool") and display:
        try:
            result = subprocess.run(
                ["xdotool", "getdisplaygeometry"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                geometry = result.stdout.strip()
                x11_available = True
            elif session_type != "wayland":
                wayland_warning = result.stderr.strip() or "xdotool could not query display geometry"
        except Exception as exc:
            wayland_warning = f"xdotool probe failed: {exc}"

    return DisplayEnvironment(
        session_type=session_type,
        display=display,
        x11_available=x11_available,
        wayland_warning=wayland_warning,
        xdotool_geometry=geometry,
    )


_cached: Optional[DisplayEnvironment] = None


def get_display_environment(refresh: bool = False) -> DisplayEnvironment:
    global _cached
    if _cached is None or refresh:
        _cached = detect_display_environment()
    return _cached


def log_startup_display_warning() -> None:
    env = get_display_environment()
    if env.wayland_warning:
        logger.warning("Display environment: %s (%s)", env.wayland_warning, env.summary())
    elif env.x11_available:
        logger.info("Display environment ready: %s", env.summary())
