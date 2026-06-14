import os
import sys
import asyncio
import logging
import socket
import subprocess
import time
import signal
from pathlib import Path
from typing import Any, List, Optional
import httpx

from dotenv import load_dotenv
from rich.console import Console, Group
from rich.panel import Panel
from rich.markdown import Markdown
from rich.rule import Rule
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from agent_framework._types import Message
import contextlib
import warnings

# Load env from root
load_dotenv(Path("/home/shaun/jarvis/.env"))

from jarvis.skills.skill_forge import load_skills_from_dir, forge_skill
from jarvis.evolution.subconscious import SubconsciousEngine

def _load_skills_silent(path):
    with open(os.devnull, 'w') as devnull:
        with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return load_skills_from_dir(path)

console = Console()
logging.basicConfig(
    filename="/home/shaun/jarvis/data/jarvis_client.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("jarvis.cli_client")

SLASH_COMMANDS = {
    "/help": "Show this help manual",
    "/new": "Start a fresh dialogue session",
    "/tasks": "Show the Jarvis implementation task list",
    "/skills": "List all loaded skill modules",
    "/clear": "Clear the screen",
    "/exit": "Exit Jarvis TUI"
}

class SlashCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        word = text.strip()
        for cmd, desc in SLASH_COMMANDS.items():
            if cmd.startswith(word):
                yield Completion(
                    cmd,
                    start_position=-len(word),
                    display=cmd,
                    display_meta=desc
                )

# Iron Man / J.A.R.V.I.S Theme (Refined for Simplicity & Usability)
PT_STYLE = Style.from_dict({
    "prompt": "bold #FFD700",
    "bottom-toolbar": "bg:ansired ansiyellow bold",
    "completion-menu.completion": "bg:#2b2b2b #FFD700",
    "completion-menu.completion.current": "bg:#FFD700 #4A0000 bold",
    "completion-menu.meta.completion": "bg:#2b2b2b #cccccc",
    "completion-menu.meta.completion.current": "bg:#FFD700 #4A0000",
})

ASCII_ART = r"""[bold #FFD700]
      _   _   ___ __   __ ___  ___ 
   _ | | /_\ | _ \ \ \ / /|_ _|/ __|
  | || |/ _ \|   / \ V /  | | \__ \
   \__//_/ \_\_|_\  \_/  |___||___/[/]
"""

def print_help():
    help_text = "\n".join([f"[bold #FFD700]{cmd}[/] - {desc}" for cmd, desc in SLASH_COMMANDS.items()])
    console.print(Panel(help_text, title="Slash Command Manual", border_style="#E63946", title_align="left"))

async def print_tasks():
    task_path = Path("/home/shaun/.gemini/antigravity-cli/brain/5ae93a25-73b8-4be0-ad5a-0a0d63cb8e35/task.md")
    if task_path.exists():
        console.print(Panel(task_path.read_text(), title="Jarvis Implementation Tasks", border_style="#FFD700"))
    else:
        console.print("[yellow]No tasks file found at active path.[/]")

def is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(('127.0.0.1', port)) == 0

class JarvisTUI:
    def __init__(self):
        self.api_key = os.environ.get("NVIDIA_API_KEY")
        self.session_id = None
        self.spawned_server = None
        self.kb = KeyBindings()
        self._setup_bindings()
        
    def _setup_bindings(self):
        @self.kb.add("enter")
        def _submit(event):
            event.current_buffer.validate_and_handle()

        @self.kb.add("escape", "enter")
        def _enter(event):
            event.current_buffer.insert_text("\n")

        @self.kb.add("/")
        def _slash_complete(event):
            event.current_buffer.insert_text("/")
            event.current_buffer.start_completion(select_first=False)

    def print_splash(self):
        reactor_graphic = (
            "      [#00F0FF]  .---.  [/]\n"
            "      [#00F0FF] /  [bold #00E5FF]⬡[/]  \\ [/]\n"
            "      [#00F0FF]| [bold #00E5FF]⬡[/] [bold #FFD700]⬢[/] [bold #00E5FF]⬡[/] |[/]\n"
            "      [#00F0FF] \\  [bold #00E5FF]⬡[/]  / [/]\n"
            "      [#00F0FF]  '---'  [/]"
        )

        from rich.table import Table
        from rich.align import Align

        info_table = Table.grid(padding=(0, 2))
        info_table.add_column()
        info_table.add_column(style="bold #E63946")
        info_table.add_column()
        info_table.add_row("[#00F0FF]⬡[/]", "STATUS:", "[bold green]ONLINE (API SERVER)[/]")
        info_table.add_row("[#00F0FF]⬡[/]", "HOST CORE:", "[bold #FFD700]NVIDIA NIM APIs[/]")
        info_table.add_row("[#00F0FF]⬡[/]", "ROUTING:", "[bold #FFD700]Stark Core Matrix[/]")
        info_table.add_row("[#00F0FF]⬡[/]", "ENDPOINT:", "[white]http://localhost:8000[/]")
        info_table.add_row("[#00F0FF]⬡[/]", "SESSION ID:", f"[white]{self.session_id}[/]")
        
        splash_table = Table.grid(padding=(0, 4))
        splash_table.add_row(reactor_graphic, info_table)

        console.print(ASCII_ART)
        console.print(Panel(
            Align.center(splash_table),
            title="[bold #FFD700]MARK XLVIII - DECOUPLED COGNITIVE INTERFACE[/]",
            border_style="#E63946",
            padding=(1, 2)
        ))
        console.print("Type [bold #FFD700]/help[/] for command manual. Press [bold cyan]Enter[/] to submit, [bold cyan]Alt+Enter[/] for multiline.\n")

    def _bottom_toolbar(self):
        return HTML(
            f" <b>Session:</b> {self.session_id} | "
            f"<b>Server:</b> localhost:8000 | "
            f"Type / for commands"
        )

    async def init(self):
        if not self.api_key:
            console.print("[bold #E63946]WARNING: NVIDIA_API_KEY environment variable is not set. API calls will fail.[/]")
            
        # 1. Check if server is running on port 8000. If not, auto-spawn.
        if not is_port_open(8000):
            console.print("[bold #00F0FF]⬡ Background API Server is offline. Starting service...[/]")
            log_dir = Path("/home/shaun/jarvis/data")
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = open(log_dir / "server.log", "a")
            
            self.spawned_server = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "jarvis.server.app:app", "--host", "127.0.0.1", "--port", "8000"],
                stdout=log_file,
                stderr=log_file,
                preexec_fn=os.setsid
            )
            
            # Wait for server to accept connections
            for _ in range(20):
                await asyncio.sleep(0.5)
                if is_port_open(8000):
                    console.print("[bold green]✓ Background API Server spawned successfully.[/]\n")
                    break
            else:
                console.print("[bold red]❌ Failed to connect to spawned API server. Verify logs at data/server.log[/]\n")
                
        # 2. Get a new session ID from the API server
        async with httpx.AsyncClient() as client:
            try:
                res = await client.post("http://127.0.0.1:8000/v1/sessions", timeout=5.0)
                res.raise_for_status()
                self.session_id = res.json()["session_id"]
            except Exception as e:
                logger.error(f"Failed to create session on API server: {e}")
                console.print(f"[bold red]❌ Connection to API server failed:[/] {e}")
                self.session_id = "local_fallback"

        # 3. Startup the subconscious routine engine (redirects routine requests to the server)
        async def _background_runner(prompt: str):
            async with httpx.AsyncClient() as client:
                try:
                    await client.post(
                        f"http://127.0.0.1:8000/v1/sessions/{self.session_id}/chat",
                        json={"message": prompt},
                        timeout=5.0
                    )
                except Exception as e:
                    logger.error(f"Failed to submit subconscious routine: {e}")
                    
        self.subconscious = SubconsciousEngine(_background_runner)
        self.subconscious.start()

    def shutdown(self):
        """Cleans up the subconscious engine and kills the spawned server if active."""
        if hasattr(self, "subconscious"):
            self.subconscious.stop()
            
        if self.spawned_server:
            console.print("\n[dim #FFD700]Shutting down background API server...[/]")
            try:
                os.killpg(os.getpgid(self.spawned_server.pid), signal.SIGTERM)
                self.spawned_server.wait(timeout=3.0)
            except Exception:
                pass
            console.print("[dim #FFD700]API Server Offline.[/]")
            
        console.print("\n[dim #FFD700]System Offline. ⚙[/]\n")

    async def handle_slash(self, cmd: str) -> bool:
        parts = cmd.split(maxsplit=1)
        base = parts[0].lower()
        if base == "/help":
            print_help()
            return True
        elif base == "/clear":
            console.clear()
            return True
        elif base == "/new":
            async with httpx.AsyncClient() as client:
                try:
                    res = await client.post("http://127.0.0.1:8000/v1/sessions", timeout=5.0)
                    self.session_id = res.json()["session_id"]
                    console.print(f"[bold #FFD700]✓ Started new dialogue session: {self.session_id}[/]\n")
                except Exception as e:
                    console.print(f"[bold red]❌ Failed to start new session:[/] {e}")
            return True
        elif base == "/tasks":
            await print_tasks()
            return True
        elif base == "/skills":
            skills_tools = _load_skills_silent(Path("/home/shaun/jarvis/skills"))
            if not skills_tools:
                console.print("[bold #FFD700]No custom skills forged yet.[/]")
            else:
                lines = [f"- [bold #FFD700]{t.name}[/]: {t.description}" for t in skills_tools]
                console.print(Panel("\n".join(lines), title="Forged Skill Modules", border_style="#E63946"))
            return True
        elif base == "/exit":
            self.shutdown()
            sys.exit(0)
        return False

    async def run_loop(self):
        self.print_splash()
        
        history_path = Path("/home/shaun/jarvis/data/pt_history.txt")
        history_path.parent.mkdir(parents=True, exist_ok=True)
        
        session_pt = PromptSession(
            completer=SlashCompleter(),
            auto_suggest=AutoSuggestFromHistory(),
            style=PT_STYLE,
            key_bindings=self.kb,
            bottom_toolbar=self._bottom_toolbar,
            complete_while_typing=True,
            enable_history_search=True,
            history=FileHistory(str(history_path)),
            multiline=True
        )
        
        while True:
            try:
                user_input = await session_pt.prompt_async(
                    HTML("<prompt>❯ </prompt>"),
                    placeholder=HTML("<style fg='#A0A0A0'>Ask anything, or type / for commands…</style>")
                )
                user_input = user_input.strip()
                if not user_input:
                    continue
                
                if user_input.startswith("/"):
                    handled = await self.handle_slash(user_input)
                    if not handled:
                        console.print(f"[bold #E63946]Unknown slash command:[/] {user_input}")
                    continue
                
                # Execute agent turn via API
                await self.execute_turn(user_input)
                
            except KeyboardInterrupt:
                console.print("\n[bold #E63946]⚡ Interrupted[/]\n")
                continue
            except EOFError:
                self.shutdown()
                break
            except Exception as e:
                console.print(f"[bold #E63946]System Error:[/] {e}")
                logger.exception("Error in main loop")

    async def execute_turn(self, prompt: str):
        from rich.live import Live
        
        # 1. Post request to submit chat input
        async with httpx.AsyncClient() as client:
            try:
                chat_res = await client.post(
                    f"http://127.0.0.1:8000/v1/sessions/{self.session_id}/chat",
                    json={"message": prompt},
                    timeout=5.0
                )
                chat_res.raise_for_status()
            except Exception as e:
                console.print(f"[bold red]❌ Failed to send prompt to API server:[/] {e}")
                return
                
        # 2. Subscribe to SSE stream and render live updates
        live = None
        reasoning_text = ""
        response_text = ""
        
        async with httpx.AsyncClient() as client:
            try:
                async with client.stream(
                    "GET", 
                    f"http://127.0.0.1:8000/v1/sessions/{self.session_id}/stream", 
                    timeout=None
                ) as response:
                    event_type = None
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                            
                        if line.startswith("event:"):
                            event_type = line.split(":", 1)[1].strip()
                        elif line.startswith("data:"):
                            data_str = line.split(":", 1)[1].strip()
                            try:
                                import json
                                data = json.loads(data_str)
                            except Exception:
                                data = {}
                                
                            # Handle different stream events
                            if event_type == "text_chunk":
                                text = data.get("text", "")
                                if text:
                                    if not live:
                                        live = Live(Group(), refresh_per_second=15, console=console)
                                        live.start()
                                    response_text += text
                                    
                                    renderables = []
                                    if reasoning_text:
                                        renderables.append(Panel(reasoning_text, title="Thinking Processes", border_style="#FFD700", title_align="left"))
                                    if response_text:
                                        renderables.append(Markdown(response_text))
                                    live.update(Group(*renderables))
                                    
                            elif event_type == "reasoning_chunk":
                                text = data.get("text", "")
                                if text:
                                    if not live:
                                        live = Live(Group(), refresh_per_second=15, console=console)
                                        live.start()
                                    reasoning_text += text
                                    
                                    renderables = []
                                    if reasoning_text:
                                        renderables.append(Panel(reasoning_text, title="Thinking Processes", border_style="#FFD700", title_align="left"))
                                    if response_text:
                                        renderables.append(Markdown(response_text))
                                    live.update(Group(*renderables))
                                    
                            elif event_type == "tool_call_start":
                                if live:
                                    live.stop()
                                    live = None
                                if response_text.strip():
                                    console.print(Markdown(response_text))
                                    response_text = ""
                                    
                                name = data.get("name", "").upper()
                                args = data.get("arguments", {})
                                console.print(f"\n[bold #E63946]⚙ TOOL EXECUTION:[/] [bold #FFD700]{name}[/]")
                                if args:
                                    for k, v in args.items():
                                        v_str = str(v).replace("\n", " ")
                                        if len(v_str) > 150:
                                            v_str = v_str[:150] + "... (truncated)"
                                        console.print(f"  [bold #FFD700]▪ {k}:[/] [white]{v_str}[/]", highlight=False)
                                        
                            elif event_type == "tool_call_complete":
                                if live:
                                    live.stop()
                                    live = None
                                if response_text.strip():
                                    console.print(Markdown(response_text))
                                    response_text = ""
                                    
                                name = data.get("name", "").upper()
                                out = data.get("output", "") or data.get("error", "")
                                if len(out) > 1000:
                                    out = out[:1000] + "\n... (truncated for readability)"
                                    
                                console.print(Panel(
                                    out,
                                    title=f"[bold #FFD700]✔ {name} OUTPUT[/]",
                                    border_style="#E63946",
                                    title_align="left",
                                    padding=(0, 1)
                                ))
                                
                            elif event_type == "turn_complete":
                                break
            except Exception as e:
                console.print(f"\n[bold #E63946]Error during SSE streaming:[/] {e}")
            finally:
                if live:
                    live.stop()
                if response_text.strip():
                    console.print(Markdown(response_text))
                console.print() # separating line

async def main():
    tui = JarvisTUI()
    await tui.init()
    await tui.run_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
