import asyncio
import logging
import time
from typing import List, Dict, Any
from rich.console import Console

console = Console()
logger = logging.getLogger("jarvis.subconscious")

class SubconsciousEngine:
    """
    The Hermes-style routine engine.
    It manages background tasks and event-driven automation.
    """
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
            "last_run": time.time()
        })
        console.print(f"\n[dim cyan]Subconscious:[/] Registered routine '{name}' (Every {interval_seconds}s)")

    async def _loop(self):
        while self._running:
            now = time.time()
            for r in self.routines:
                if now - r["last_run"] >= r["interval"]:
                    r["last_run"] = now
                    console.print(f"\n[dim cyan]Subconscious:[/] Triggering routine '{r['name']}'...")
                    try:
                        await self.agent_runner(r["prompt"])
                    except Exception as e:
                        logger.error(f"Routine {r['name']} failed: {e}")
                        console.print(f"[bold red]Routine {r['name']} failed:[/] {e}")
            await asyncio.sleep(1)

    def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())
        console.print("[dim cyan]⬡ Subconscious Engine Online. Evolution Active.[/]")
        
    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
