import pytest
import os
import json
from unittest.mock import AsyncMock, MagicMock, patch
from skills.web_research import web_search, web_extract

@pytest.mark.asyncio
async def test_web_search_tavily_success():
    """Verify that web_search uses Tavily when the API key is present."""
    mock_tavily_client = MagicMock()
    mock_tavily_client.search = AsyncMock(return_value={
        "results": [
            {"title": "Test Tavily Title", "url": "https://example.com/tavily", "content": "Tavily Content"}
        ]
    })
    
    with patch("skills.web_research.get_tavily_client", return_value=mock_tavily_client):
        result_str = await web_search("test query")
        result = json.loads(result_str)
        
        assert result["success"] is True
        assert len(result["results"]) == 1
        assert result["results"][0]["title"] == "Test Tavily Title"
        assert result["results"][0]["engine"] == "tavily"

@pytest.mark.asyncio
async def test_web_search_ddgs_fallback():
    """Verify that web_search falls back to DuckDuckGo when Tavily fails or is absent."""
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = [
        {"title": "Test DDG Title", "href": "https://example.com/ddg", "body": "DDG Body"}
    ]
    
    # Force get_tavily_client to return None (simulating no API key)
    with patch("skills.web_research.get_tavily_client", return_value=None):
        with patch("skills.web_research.DDGS") as mock_ddgs_class:
            mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs_instance
            
            result_str = await web_search("test query")
            result = json.loads(result_str)
            
            assert result["success"] is True
            assert len(result["results"]) == 1
            assert result["results"][0]["title"] == "Test DDG Title"
            assert result["results"][0]["engine"] == "ddgs"

@pytest.mark.asyncio
async def test_web_extract_firecrawl_success():
    """Verify that web_extract uses Firecrawl when the API key is present."""
    mock_firecrawl_app = MagicMock()
    mock_firecrawl_app.scrape_url = AsyncMock(return_value={
        "markdown": "Clean Markdown from Firecrawl"
    })
    
    with patch("skills.web_research.get_firecrawl_app", return_value=mock_firecrawl_app):
        result = await web_extract("https://example.com/page")
        assert result == "Clean Markdown from Firecrawl"

@pytest.mark.asyncio
async def test_web_extract_local_fallback():
    """Verify that web_extract falls back to manual HTTP scraper when Firecrawl fails or is absent."""
    mock_response = MagicMock()
    mock_response.content = b"<html><body><script>javascript</script><nav>Navbar</nav><div>Main Webpage Content</div></body></html>"
    mock_response.raise_for_status = MagicMock()
    
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    
    with patch("skills.web_research.get_firecrawl_app", return_value=None):
        with patch("skills.web_research.httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            result = await web_extract("https://example.com/page")
            assert "Main Webpage Content" in result
            assert "javascript" not in result
            assert "Navbar" not in result
