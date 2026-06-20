import pytest
from unittest.mock import patch

from jarvis.core.display_env import DisplayEnvironment, detect_display_environment


def test_detect_display_environment_wayland_warning():
    with patch.dict("os.environ", {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"}, clear=False):
        with patch("jarvis.core.display_env.shutil.which", return_value="/usr/bin/xdotool"):
            with patch("jarvis.core.display_env.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 1
                mock_run.return_value.stderr = "XGetWindowProperty failed"
                env = detect_display_environment()
    assert env.session_type == "wayland"
    assert env.wayland_warning is not None
    assert env.x11_available is False


def test_display_environment_desktop_ready():
    env = DisplayEnvironment(
        session_type="x11",
        display=":0",
        x11_available=True,
        wayland_warning=None,
        xdotool_geometry="1920 1080",
    )
    assert env.desktop_automation_ready is True
    assert "1920" in env.summary()
