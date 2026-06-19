import os
import json
import logging
import asyncio
from typing import Optional
from playwright.async_api import async_playwright
from agent_framework import tool
from jarvis.config.paths import get_webvision_dir

logger = logging.getLogger("jarvis.skills.webvision")

_playwright = None
_browser = None
_page = None

async def get_page():
    global _playwright, _browser, _page
    try:
        if _page is not None and not _page.is_closed():
            return _page
    except Exception:
        _page = None
        
    try:
        if _playwright is None:
            _playwright = await async_playwright().start()
        if _browser is None or not _browser.is_connected():
            _browser = await _playwright.chromium.launch(headless=True)
        _page = await _browser.new_page()
        return _page
    except Exception as e:
        logger.error(f"Failed to initialize Playwright browser context: {e}")
        await cleanup_browser()
        raise e

async def cleanup_browser():
    global _playwright, _browser, _page
    try:
        if _page is not None:
            await _page.close()
    except Exception:
        pass
    try:
        if _browser is not None:
            await _browser.close()
    except Exception:
        pass
    try:
        if _playwright is not None:
            await _playwright.stop()
    except Exception:
        pass
    _page = None
    _browser = None
    _playwright = None

@tool(approval_mode="never_require")
async def webvision_navigate(url: str, wait_selector: Optional[str] = None) -> str:
    """
    HUD WebVision: Navigate the optical uplink to a webpage. Waits for hydration
    and returns the rendered text content.
    Args:
        url: The absolute HTTP/HTTPS webpage URL to load.
        wait_selector: Optional CSS selector to wait for before extracting text.
    Returns:
        Rendered text content of the page or error report.
    """
    # Simple SSRF protection
    lower_url = url.lower().strip()
    if not (lower_url.startswith("http://") or lower_url.startswith("https://")):
        return json.dumps({"success": False, "error": "Only HTTP/HTTPS URLs are supported."})
    for blocked in ["localhost", "127.0.0.1", "169.254.169.254", "0.0.0.0"]:
        if blocked in lower_url:
            return json.dumps({"success": False, "error": f"Access to internal network resource '{blocked}' is blocked."})

    try:
        page = await get_page()
        logger.info(f"WebVision navigating to: {url}")
        
        await page.goto(url, wait_until="load", timeout=20000)
        
        if wait_selector:
            logger.info(f"WebVision waiting for selector: {wait_selector}")
            await page.wait_for_selector(wait_selector, state="visible", timeout=10000)
        else:
            try:
                await page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
                
        text = await page.evaluate("() => document.body.innerText")
        lines = (line.strip() for line in text.splitlines())
        clean_text = '\n'.join(line for line in lines if line)
        
        if len(clean_text) > 8000:
            clean_text = clean_text[:8000] + "\n... (truncated for brevity)"
            
        return clean_text
    except Exception as e:
        logger.error(f"WebVision navigation failed: {e}")
        return json.dumps({"success": False, "error": f"Navigation failed: {e}"})

@tool(approval_mode="never_require")
async def webvision_interact(selector: str, action: str, text: Optional[str] = None) -> str:
    """
    HUD WebVision: Perform UI actions (click, fill/type, press) on page elements.
    Args:
        selector: CSS selector for the target element (e.g. 'button#login', 'input[name="q"]').
        action: The action to perform. One of: 'click', 'fill', 'press'.
        text: Required text value for 'fill' or key name for 'press' (e.g. 'Enter').
    Returns:
        JSON string reporting success state.
    """
    try:
        page = await get_page()
        if page.url == "about:blank":
            return json.dumps({"success": False, "error": "No webpage loaded. Run webvision_navigate first."})

        await page.wait_for_selector(selector, state="visible", timeout=8000)
        
        action_lower = action.lower().strip()
        if action_lower == "click":
            await page.click(selector, timeout=5000)
            logger.info(f"WebVision clicked element: {selector}")
            msg = f"Successfully clicked '{selector}'"
        elif action_lower == "fill":
            if text is None:
                return json.dumps({"success": False, "error": "Missing 'text' argument for 'fill' action."})
            await page.fill(selector, text, timeout=5000)
            logger.info(f"WebVision filled element: {selector}")
            msg = f"Successfully filled '{selector}' with text"
        elif action_lower == "press":
            if text is None:
                return json.dumps({"success": False, "error": "Missing 'text' argument for 'press' action (e.g. 'Enter')."})
            await page.press(selector, text, timeout=5000)
            logger.info(f"WebVision pressed key: {text} on {selector}")
            msg = f"Successfully pressed key '{text}' on '{selector}'"
        else:
            return json.dumps({"success": False, "error": f"Unsupported action '{action}'. Use 'click', 'fill', or 'press'."})

        await asyncio.sleep(1)
        return json.dumps({"success": True, "message": msg})
    except Exception as e:
        logger.error(f"WebVision interaction failed: {e}")
        return json.dumps({"success": False, "error": f"Interaction failed: {e}"})

@tool(approval_mode="never_require")
async def webvision_capture(filename: str = "hud_capture.png") -> str:
    """
    HUD WebVision: Capture a PNG screenshot of the current page viewport and save
    it under the workspace folder 'webvision/'.
    Args:
        filename: Target filename (e.g. 'login_result.png').
    Returns:
        JSON string containing success message and the saved workspace path.
    """
    try:
        page = await get_page()
        if page.url == "about:blank":
            return json.dumps({"success": False, "error": "No webpage loaded. Run webvision_navigate first."})

        webvision_dir = str(get_webvision_dir())
        os.makedirs(webvision_dir, exist_ok=True)
        
        file_path = os.path.join(webvision_dir, filename)
        await page.screenshot(path=file_path)
        
        logger.info(f"WebVision HUD capture saved: {file_path}")
        return json.dumps({
            "success": True,
            "message": "HUD display buffer captured successfully.",
            "path": f"webvision/{filename}"
        })
    except Exception as e:
        logger.error(f"WebVision capture failed: {e}")
        return json.dumps({"success": False, "error": f"Capture failed: {e}"})

@tool(approval_mode="never_require")
async def webvision_close() -> str:
    """
    HUD WebVision: Terminate the browser session and close the optical uplink connection.
    Returns:
        JSON string reporting connection closure.
    """
    await cleanup_browser()
    logger.info("WebVision session terminated.")
    return json.dumps({"success": True, "message": "HUD WebVision optical uplink terminated successfully."})
