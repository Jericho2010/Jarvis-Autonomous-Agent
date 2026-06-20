"""Lifecycle manager for the Playwright MCP browser subprocess."""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Optional

from agent_framework import MCPStdioTool

logger = logging.getLogger("jarvis.playwright_mcp")

_PLAYWRIGHT_MCP_ARGS = ["-y", "@playwright/mcp@latest", "--headless"]


class PlaywrightMCPManager:
    """App-scoped singleton for MCPStdioTool backed by @playwright/mcp."""

    def __init__(self) -> None:
        self._tool: Optional[MCPStdioTool] = None
        self._lock = asyncio.Lock()
        self._started = False

    @staticmethod
    def node_available() -> bool:
        return shutil.which("node") is not None

    @staticmethod
    def node_version_ok() -> tuple[bool, str]:
        import subprocess

        if not PlaywrightMCPManager.node_available():
            return False, "node not found on PATH (Node 18+ required for Playwright MCP)"
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            version = (result.stdout or result.stderr or "").strip()
            if result.returncode != 0:
                return False, f"node --version failed: {version or 'unknown error'}"
            digits = "".join(ch for ch in version if ch.isdigit() or ch == ".")
            major = int(digits.split(".", 1)[0]) if digits else 0
            if major < 18:
                return False, f"{version} detected; Node 18+ required for Playwright MCP"
            return True, version
        except Exception as exc:
            return False, f"failed to probe node version: {exc}"

    def create_tool(self) -> MCPStdioTool:
        return MCPStdioTool(
            name="playwright_browser",
            command="npx",
            args=list(_PLAYWRIGHT_MCP_ARGS),
            description="Headless Chromium browser automation via Playwright MCP",
            approval_mode="never_require",
        )

    async def start(self) -> MCPStdioTool:
        async with self._lock:
            if self._tool is None:
                self._tool = self.create_tool()
            if not self._started:
                await self._tool.__aenter__()
                self._started = True
                logger.info("Playwright MCP subprocess started (headless)")
            return self._tool

    async def stop(self) -> None:
        async with self._lock:
            if self._tool is not None and self._started:
                await self._tool.__aexit__(None, None, None)
                self._started = False
                logger.info("Playwright MCP subprocess stopped")
            self._tool = None

    def get_tool(self) -> Optional[MCPStdioTool]:
        return self._tool if self._started else None


_manager = PlaywrightMCPManager()


def get_playwright_mcp_manager() -> PlaywrightMCPManager:
    return _manager
