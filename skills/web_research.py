import os
import json
import logging
import asyncio
from typing import Optional
import httpx
from lxml import html
from ddgs import DDGS
from agent_framework import tool

logger = logging.getLogger("jarvis.skills.web_research")

_async_tavily_client = None
_async_firecrawl_app = None

def get_tavily_client():
    global _async_tavily_client
    if _async_tavily_client is not None:
        return _async_tavily_client
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return None
    try:
        from tavily import AsyncTavilyClient
        _async_tavily_client = AsyncTavilyClient(api_key=api_key)
        return _async_tavily_client
    except ImportError:
        logger.warning("tavily-python package not installed but TAVILY_API_KEY is present.")
        return None

def get_firecrawl_app():
    global _async_firecrawl_app
    if _async_firecrawl_app is not None:
        return _async_firecrawl_app
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        return None
    try:
        from firecrawl import AsyncFirecrawlApp
        _async_firecrawl_app = AsyncFirecrawlApp(api_key=api_key)
        return _async_firecrawl_app
    except ImportError:
        logger.warning("firecrawl-py package not installed but FIRECRAWL_API_KEY is present.")
        return None

@tool(approval_mode="never_require")
async def web_search(query: str, limit: int = 5) -> str:
    """
    Search the web for up-to-date information. Uses Tavily semantic search if available,
    otherwise falls back to DuckDuckGo.
    Args:
        query: The search query string.
        limit: The maximum number of results to return (default is 5).
    Returns:
        JSON string containing list of search hits.
    """
    limit = min(max(int(limit), 1), 20)
    tavily = get_tavily_client()
    
    if tavily:
        logger.info(f"Using Async Tavily search for query: '{query}'")
        try:
            response = await tavily.search(query, max_results=limit)
            results = response.get("results", [])
            web_results = []
            for i, r in enumerate(results):
                web_results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "description": r.get("content", ""),
                    "position": i + 1,
                    "engine": "tavily"
                })
            return json.dumps({"success": True, "results": web_results}, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Tavily search failed, falling back to DuckDuckGo: {e}")
            
    # Fallback to DuckDuckGo (running sync inside a thread pool to avoid blocking)
    logger.info(f"Using DuckDuckGo search for query: '{query}'")
    try:
        def sync_search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=limit))
                
        results = await asyncio.to_thread(sync_search)
        web_results = []
        for i, r in enumerate(results):
            web_results.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "description": r.get("body", ""),
                "position": i + 1,
                "engine": "ddgs"
            })
        return json.dumps({"success": True, "results": web_results}, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"DuckDuckGo fallback search failed: {e}")
        return json.dumps({"success": False, "error": f"Search failed: {e}"})

@tool(approval_mode="never_require")
async def web_extract(url: str) -> str:
    """
    Retrieve and parse the text content of a webpage URL. Uses Firecrawl to convert
    the page to clean markdown if available, otherwise crawls locally and sanitizes the text.
    Args:
        url: The absolute HTTP or HTTPS URL to read.
    Returns:
        Cleaned, human-readable webpage content.
    """
    # Simple SSRF protection
    lower_url = url.lower().strip()
    if not (lower_url.startswith("http://") or lower_url.startswith("https://")):
        return json.dumps({"success": False, "error": "Invalid protocol. Only HTTP/HTTPS URLs are supported."})
        
    for blocked in ["localhost", "127.0.0.1", "169.254.169.254", "0.0.0.0"]:
        if blocked in lower_url:
            return json.dumps({"success": False, "error": f"Access to internal network resource '{blocked}' is blocked."})

    firecrawl = get_firecrawl_app()
    if firecrawl:
        logger.info(f"Using Async Firecrawl scraping for: {url}")
        try:
            result = await firecrawl.scrape_url(url, params={'formats': ['markdown']})
            if isinstance(result, dict):
                clean_text = result.get('markdown') or result.get('content') or ""
            else:
                clean_text = getattr(result, 'markdown', None) or getattr(result, 'content', None) or str(result)
                
            if clean_text:
                if len(clean_text) > 8000:
                    clean_text = clean_text[:8000] + "\n... (truncated for brevity)"
                return clean_text
        except Exception as e:
            logger.warning(f"Firecrawl scraping failed, falling back to local HTTP scraper: {e}")

    # Fallback to manual HTTP scrape
    logger.info(f"Using manual Async HTTP scraper for: {url}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, headers=headers, timeout=12.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            
            # Parsing HTML is fast but we run the text cleanup in a thread to keep things fully non-blocking
            def parse_html():
                tree = html.fromstring(response.content)
                for element in tree.xpath('//script | //style | //noscript | //header | //footer | //nav | //iframe'):
                    element.getparent().remove(element)
                text = tree.text_content()
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase for line in lines for phrase in line.split("  "))
                return '\n'.join(chunk for chunk in chunks if chunk)
                
            clean_text = await asyncio.to_thread(parse_html)
            
            if len(clean_text) > 8000:
                clean_text = clean_text[:8000] + "\n... (truncated for brevity)"
                
            return clean_text
    except Exception as e:
        logger.error(f"Manual HTTP scraper failed: {e}")
        return json.dumps({"success": False, "error": f"Extraction failed: {e}"})
