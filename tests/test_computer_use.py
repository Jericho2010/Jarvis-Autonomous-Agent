import pytest
import json
from unittest.mock import MagicMock, patch
from skills.computer_use import (
    stark_os_retinal_hud,
    stark_os_kinetic_click,
    stark_os_kinetic_double_click,
    stark_os_kinetic_scroll,
    stark_os_kinetic_type,
    stark_os_kinetic_key,
    stark_os_armor_list_windows,
    stark_os_armor_focus_window
)

def test_stark_os_retinal_hud_success():
    mock_run = MagicMock()
    mock_run.returncode = 0
    
    with patch("skills.computer_use.subprocess.run", return_value=mock_run):
        with patch("skills.computer_use.os.makedirs") as mock_makedirs:
            result_str = stark_os_retinal_hud("test.png")
            result = json.loads(result_str)
            assert result["success"] is True
            assert "Retinal HUD display buffer captured" in result["message"]
            assert result["path"] == "webvision/test.png"

def test_stark_os_kinetic_click_success():
    mock_run = MagicMock()
    mock_run.returncode = 0
    
    with patch("skills.computer_use.subprocess.run", return_value=mock_run) as mock_sub:
        result_str = stark_os_kinetic_click(100, 200)
        result = json.loads(result_str)
        assert result["success"] is True
        assert "Successfully left-clicked" in result["message"]
        mock_sub.assert_called_once_with(
            ["xdotool", "mousemove", "100", "200", "click", "1"],
            capture_output=True,
            text=True
        )

def test_stark_os_kinetic_double_click_success():
    mock_run = MagicMock()
    mock_run.returncode = 0
    
    with patch("skills.computer_use.subprocess.run", return_value=mock_run) as mock_sub:
        result_str = stark_os_kinetic_double_click(300, 400)
        result = json.loads(result_str)
        assert result["success"] is True
        assert "Successfully double-clicked" in result["message"]
        mock_sub.assert_called_once_with(
            ["xdotool", "mousemove", "300", "400", "click", "--repeat", "2", "--delay", "100", "1"],
            capture_output=True,
            text=True
        )

def test_stark_os_kinetic_scroll_success():
    mock_run = MagicMock()
    mock_run.returncode = 0
    
    with patch("skills.computer_use.subprocess.run", return_value=mock_run) as mock_sub:
        result_str = stark_os_kinetic_scroll("down", 5)
        result = json.loads(result_str)
        assert result["success"] is True
        assert "Successfully scrolled down 5 times" in result["message"]
        mock_sub.assert_called_once_with(
            ["xdotool", "click", "--repeat", "5", "--delay", "50", "5"],
            capture_output=True,
            text=True
        )

def test_stark_os_kinetic_type_success():
    mock_run = MagicMock()
    mock_run.returncode = 0
    
    with patch("skills.computer_use.subprocess.run", return_value=mock_run) as mock_sub:
        result_str = stark_os_kinetic_type("Stark OS")
        result = json.loads(result_str)
        assert result["success"] is True
        assert "Successfully typed" in result["message"]
        mock_sub.assert_called_once_with(
            ["xdotool", "type", "--delay", "50", "Stark OS"],
            capture_output=True,
            text=True
        )

def test_stark_os_kinetic_key_success():
    mock_run = MagicMock()
    mock_run.returncode = 0
    
    with patch("skills.computer_use.subprocess.run", return_value=mock_run) as mock_sub:
        result_str = stark_os_kinetic_key("ctrl+c")
        result = json.loads(result_str)
        assert result["success"] is True
        assert "pressed key sequence: ctrl+c" in result["message"]
        mock_sub.assert_called_once_with(
            ["xdotool", "key", "ctrl+c"],
            capture_output=True,
            text=True
        )

def test_stark_os_armor_list_windows_success():
    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stdout = (
        "0x03c00003  0 zbook Firefox Web Browser\n"
        "0x04600006  0 zbook Terminal\n"
    )
    
    with patch("skills.computer_use.subprocess.run", return_value=mock_run) as mock_sub:
        result_str = stark_os_armor_list_windows()
        result = json.loads(result_str)
        assert result["success"] is True
        assert len(result["windows"]) == 2
        assert result["windows"][0]["id"] == "0x03c00003"
        assert result["windows"][0]["title"] == "Firefox Web Browser"

def test_stark_os_armor_focus_window_success():
    mock_run = MagicMock()
    mock_run.returncode = 0
    
    with patch("skills.computer_use.subprocess.run", return_value=mock_run) as mock_sub:
        result_str = stark_os_armor_focus_window("Firefox")
        result = json.loads(result_str)
        assert result["success"] is True
        assert "Successfully activated window matching 'Firefox'" in result["message"]
        mock_sub.assert_called_once_with(
            ["wmctrl", "-a", "Firefox"],
            capture_output=True,
            text=True
        )
