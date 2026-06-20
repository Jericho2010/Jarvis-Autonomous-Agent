import asyncio
import logging
import time
from typing import Any, Dict, List

from rich.console import Console

console = Console()
logger = logging.getLogger("jarvis.routines")


class BackgroundRoutineEngine:
    """Interval-based background routine runner (TUI). Not the nightly subconscious cron."""

    def __init__(self, agent_runner):
        self.agent_runner = agent_runner
        self._running = False
        self.routines: List[Dict[str, Any]] = []
        self._task = None

    def add_routine(self, interval_seconds: int, prompt: str, name: str):
        self.routines.append({
            "interval": interval_seconds,
            "prompt": prompt,
            "name": name,
            "last_run": time.time(),
        })
        console.print(f"\n[#00E5FF]⬡ Routines:[/] Registered '{name}' (every {interval_seconds}s)")

    async def _loop(self):
        while self._running:
            now = time.time()
            for r in self.routines:
                if now - r["last_run"] >= r["interval"]:
                    r["last_run"] = now
                    console.print(f"\n[#00E5FF]⬡ Routines:[/] Triggering '{r['name']}'...")
                    try:
                        await self.agent_runner(r["prompt"])
                    except Exception as e:
                        logger.error("Routine %s failed: %s", r["name"], e)
                        console.print(f"[bold red]Routine {r['name']} failed:[/] {e}")
            await asyncio.sleep(1)

    def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())
        if self.routines:
            console.print("[bold #00E5FF]⬡ Background routine engine online.[/]")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()


# Backward-compatible alias
SubconsciousEngine = BackgroundRoutineEngine
