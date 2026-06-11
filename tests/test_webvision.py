import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from skills.webvision import webvision_navigate, webvision_interact, webvision_capture, webvision_close

@pytest.mark.asyncio
async def test_webvision_navigate_success():
    """Verify that webvision_navigate opens the page and returns clean text content."""
    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value="  Test Page Content  \n\n  Subcontent ")
    
    with patch("skills.webvision.get_page", return_value=mock_page):
        result = await webvision_navigate("https://example.com")
        assert result == "Test Page Content\nSubcontent"
        mock_page.goto.assert_called_once_with("https://example.com", wait_until="load", timeout=20000)

@pytest.mark.asyncio
async def test_webvision_interact_click():
    """Verify that webvision_interact performs a click operation on a selector."""
    mock_page = AsyncMock()
    mock_page.url = "https://example.com/form"
    
    with patch("skills.webvision.get_page", return_value=mock_page):
        result_str = await webvision_interact("button#submit", "click")
        result = json.loads(result_str)
        
        assert result["success"] is True
        assert "Successfully clicked" in result["message"]
        mock_page.click.assert_called_once_with("button#submit", timeout=5000)

@pytest.mark.asyncio
async def test_webvision_interact_fill():
    """Verify that webvision_interact performs a fill text operation on an input selector."""
    mock_page = AsyncMock()
    mock_page.url = "https://example.com/form"
    
    with patch("skills.webvision.get_page", return_value=mock_page):
        result_str = await webvision_interact("input#username", "fill", "stark")
        result = json.loads(result_str)
        
        assert result["success"] is True
        assert "Successfully filled" in result["message"]
        mock_page.fill.assert_called_once_with("input#username", "stark", timeout=5000)

@pytest.mark.asyncio
async def test_webvision_capture_success():
    """Verify that webvision_capture takes viewport screenshot and saves to the correct path."""
    mock_page = AsyncMock()
    mock_page.url = "https://example.com"
    
    with patch("skills.webvision.get_page", return_value=mock_page):
        with patch("skills.webvision.os.makedirs") as mock_makedirs:
            result_str = await webvision_capture("hud_capture_test.png")
            result = json.loads(result_str)
            
            assert result["success"] is True
            assert "HUD display buffer captured" in result["message"]
            assert result["path"] == "webvision/hud_capture_test.png"
            mock_page.screenshot.assert_called_once()
