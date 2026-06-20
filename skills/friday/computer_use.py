import os
import json
import logging
import subprocess
from typing import Optional
from agent_framework import tool
from jarvis.config.paths import capture_public_url, get_webvision_dir, get_workspace_root
from jarvis.core.display_env import get_display_environment

logger = logging.getLogger("jarvis.skills.computer_use")


def _desktop_guard_message() -> Optional[str]:
    env = get_display_environment()
    if env.desktop_automation_ready:
        return None
    return env.wayland_warning or "Desktop automation unavailable (X11 display not detected)."


@tool(approval_mode="never_require")
def stark_os_retinal_hud(filename: str = "retinal_capture.png") -> str:
    """
    Stark OS-Uplink: Capture the entire screen (Retinal HUD) and save it in the workspace folder.
    Args:
        filename: Target filename for the screenshot (e.g. 'desktop_capture.png').
    Returns:
        JSON report containing success state and file path.
    """
    capture_dir = str(get_webvision_dir())
    os.makedirs(capture_dir, exist_ok=True)
    file_path = os.path.join(capture_dir, filename)
    
    # Try with silent flag -z first, fall back to standard if error
    try:
        res = subprocess.run(
            ["scrot", "-z", file_path],
            capture_output=True,
            text=True,
            cwd=str(get_workspace_root())
        )
        if res.returncode != 0:
            res = subprocess.run(
                ["scrot", file_path],
                capture_output=True,
                text=True,
                cwd=str(get_workspace_root())
            )
        
        if res.returncode == 0:
            logger.info(f"Stark OS-Uplink: Saved retinal capture to {file_path}")
            return json.dumps({
                "success": True,
                "message": "Retinal HUD display buffer captured successfully.",
                "path": f"webvision/{filename}",
                "url": capture_public_url(filename),
            })
        else:
            err = res.stderr or "Unknown error"
            return json.dumps({"success": False, "error": f"scrot failed: {err}"})
    except Exception as e:
        logger.error(f"Retinal capture execution failed: {e}")
        return json.dumps({"success": False, "error": str(e)})

@tool(approval_mode="always_require")
def stark_os_kinetic_click(x: int, y: int) -> str:
    """
    Stark OS-Uplink: Move cursor to coordinates (x, y) and perform a left-click.
    Args:
        x: Horizontal pixel coordinate.
        y: Vertical pixel coordinate.
    Returns:
        JSON report of operation success.
    """
    guard = _desktop_guard_message()
    if guard:
        return json.dumps({"success": False, "error": guard})
    try:
        res = subprocess.run(
            ["xdotool", "mousemove", str(x), str(y), "click", "1"],
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            return json.dumps({"success": True, "message": f"Successfully left-clicked at coordinate ({x}, {y})"})
        return json.dumps({"success": False, "error": res.stderr or "xdotool click failed"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

@tool(approval_mode="always_require")
def stark_os_kinetic_double_click(x: int, y: int) -> str:
    """
    Stark OS-Uplink: Move cursor to coordinates (x, y) and perform a double left-click.
    Args:
        x: Horizontal pixel coordinate.
        y: Vertical pixel coordinate.
    Returns:
        JSON report of operation success.
    """
    guard = _desktop_guard_message()
    if guard:
        return json.dumps({"success": False, "error": guard})
    try:
        res = subprocess.run(
            ["xdotool", "mousemove", str(x), str(y), "click", "--repeat", "2", "--delay", "100", "1"],
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            return json.dumps({"success": True, "message": f"Successfully double-clicked at coordinate ({x}, {y})"})
        return json.dumps({"success": False, "error": res.stderr or "xdotool double click failed"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

@tool(approval_mode="always_require")
def stark_os_kinetic_scroll(direction: str, clicks: int = 3) -> str:
    """
    Stark OS-Uplink: Perform a scroll wheel action.
    Args:
        direction: The scroll direction. Must be 'up' or 'down'.
        clicks: The number of scroll increments to execute.
    Returns:
        JSON report of operation success.
    """
    guard = _desktop_guard_message()
    if guard:
        return json.dumps({"success": False, "error": guard})
    dir_lower = direction.lower().strip()
    if dir_lower == "up":
        button = "4"
    elif dir_lower == "down":
        button = "5"
    else:
        return json.dumps({"success": False, "error": "Invalid scroll direction. Use 'up' or 'down'."})
        
    try:
        res = subprocess.run(
            ["xdotool", "click", "--repeat", str(clicks), "--delay", "50", button],
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            return json.dumps({"success": True, "message": f"Successfully scrolled {dir_lower} {clicks} times"})
        return json.dumps({"success": False, "error": res.stderr or "xdotool scroll failed"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

@tool(approval_mode="always_require")
def stark_os_kinetic_type(text: str) -> str:
    """
    Stark OS-Uplink: Type text at the current keyboard cursor location.
    Args:
        text: The text string to type.
    Returns:
        JSON report of operation success.
    """
    guard = _desktop_guard_message()
    if guard:
        return json.dumps({"success": False, "error": guard})
    try:
        res = subprocess.run(
            ["xdotool", "type", "--delay", "50", text],
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            return json.dumps({"success": True, "message": "Successfully typed text segment"})
        return json.dumps({"success": False, "error": res.stderr or "xdotool type failed"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

@tool(approval_mode="always_require")
def stark_os_kinetic_key(key: str) -> str:
    """
    Stark OS-Uplink: Press a key or combination of keys (e.g. 'Return', 'ctrl+alt+t', 'BackSpace').
    Args:
        key: The key name or keyboard shortcut sequence.
    Returns:
        JSON report of operation success.
    """
    guard = _desktop_guard_message()
    if guard:
        return json.dumps({"success": False, "error": guard})
    try:
        res = subprocess.run(
            ["xdotool", "key", key],
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            return json.dumps({"success": True, "message": f"Successfully pressed key sequence: {key}"})
        return json.dumps({"success": False, "error": res.stderr or "xdotool key failed"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

@tool(approval_mode="never_require")
def stark_os_armor_list_windows() -> str:
    """
    Stark OS-Uplink: Query active system windows and return their metadata in a JSON array.
    Returns:
        JSON array string representing window titles and workspace IDs.
    """
    try:
        res = subprocess.run(
            ["wmctrl", "-l"],
            capture_output=True,
            text=True
        )
        if res.returncode != 0:
            return json.dumps({"success": False, "error": res.stderr or "wmctrl -l failed"})
            
        windows = []
        for line in res.stdout.splitlines():
            parts = line.split(maxsplit=3)
            if len(parts) >= 4:
                windows.append({
                    "id": parts[0],
                    "desktop": parts[1],
                    "host": parts[2],
                    "title": parts[3]
                })
        return json.dumps({"success": True, "windows": windows})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

@tool(approval_mode="always_require")
def stark_os_armor_focus_window(title_pattern: str) -> str:
    """
    Stark OS-Uplink: Switch focus and bring a window matching the title pattern to the foreground.
    Args:
        title_pattern: Substring match pattern of the target window title.
    Returns:
        JSON report of operation success.
    """
    guard = _desktop_guard_message()
    if guard:
        return json.dumps({"success": False, "error": guard})
    try:
        res = subprocess.run(
            ["wmctrl", "-a", title_pattern],
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            return json.dumps({"success": True, "message": f"Successfully activated window matching '{title_pattern}'"})
        return json.dumps({"success": False, "error": res.stderr or f"Failed to focus window matching '{title_pattern}'"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
