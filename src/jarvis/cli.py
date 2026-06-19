import os
import sys
import asyncio
import logging
import socket
import subprocess
import time
import signal
from pathlib import Path
from typing import Any, List, Optional, Tuple
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
from prompt_toolkit.patch_stdout import patch_stdout

from jarvis.config.paths import (
    get_data_dir,
    get_env_file,
    get_skills_dir,
    get_workspace_root,
)

# Load env from root
load_dotenv(get_env_file())

def check_system_dependencies():
    import shutil
    missing = []
    for cmd in ["xdotool", "scrot", "wmctrl"]:
        if not shutil.which(cmd):
            missing.append(cmd)
    try:
        import playwright
    except ImportError:
        missing.append("playwright (python package)")
        
    if missing:
        console.print(f"\n[bold #FFD700]⚠ Stark System Diagnostics // Missing dependencies: {', '.join(missing)}[/bold #FFD700]")
        console.print("[dim #FFD700]Please run: sudo apt install scrot xdotool wmctrl && playwright install[/dim]\n")
        logger.warning(f"Startup Diagnostics: Missing dependencies {missing}")

from jarvis.skills.skill_forge import load_skills_from_dir, forge_skill
from jarvis.evolution.subconscious import SubconsciousEngine

def _load_skills_silent(path):
    with open(os.devnull, 'w') as devnull:
        with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return load_skills_from_dir(path)

console = Console()
raw_console = Console(file=sys.__stdout__)
logging.basicConfig(
    filename=str(get_data_dir() / "jarvis_client.log"),
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("jarvis.cli_client")

SLASH_COMMANDS = {
    "/help": "Show this help manual",
    "/new": "Start a fresh dialogue session",
    "/switch": "Switch to an existing session: /switch [session_id|index]",
    "/agent": "Switch active session agent: /agent <homer|friday|plato|jarvis>",
    "/tasks": "Show the Jarvis implementation task list",
    "/skills": "List all loaded skill modules",
    "/models": "List available cognitive models",
    "/model": "Set primary model: /model <name|index>",
    "/subagents": "List cognitive sub-agent profiles",
    "/voicemode": "Toggle spoken butler voice: /voicemode [on|off]",
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

class FileMentionCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        idx = text.rfind('@')
        if idx == -1:
            return
        if idx > 0 and not text[idx - 1].isspace():
            return
            
        mention_prefix = text[idx + 1:]
        try:
            path_prefix = Path(mention_prefix)
            if mention_prefix.endswith('/') or mention_prefix.endswith(os.path.sep):
                scan_dir = Path(".") / path_prefix
                file_prefix = ""
            else:
                scan_dir = Path(".") / path_prefix.parent
                file_prefix = path_prefix.name
                
            if not scan_dir.exists() or not scan_dir.is_dir():
                return
                
            for entry in scan_dir.iterdir():
                if entry.name.startswith(file_prefix):
                    if entry.name.startswith('.') and not file_prefix.startswith('.'):
                        continue
                    if entry.name in ('.git', '.venv', '__pycache__', 'node_modules'):
                        continue
                        
                    rel_path = entry.relative_to(Path("."))
                    display_name = entry.name
                    if entry.is_dir():
                        display_name += "/"
                        completion_text = str(rel_path) + "/"
                    else:
                        completion_text = str(rel_path)
                        
                    yield Completion(
                        completion_text,
                        start_position=-len(mention_prefix),
                        display=display_name,
                        display_meta="File Attachment"
                    )
        except Exception:
            pass

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

def check_jarvis_service(port: int) -> tuple[bool, bool]:
    """
    Checks if the port is open and returns if it runs J.A.R.V.I.S. and if it's open.
    Returns: (is_jarvis, is_open)
    """
    is_open = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return False, False
            is_open = True
        import urllib.request
        import json
        url = f"http://127.0.0.1:{port}/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=1.0) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                return data.get("service") == "jarvis", True
    except Exception:
        pass
    return False, is_open


def find_free_port(start_port: int) -> int:
    """Scans for the next free port sequentially."""
    port = start_port
    while port < start_port + 100:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
        port += 1
    return start_port

PID_FILE = get_data_dir() / "server.pid"

def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False

def get_running_server_info() -> tuple[Optional[int], Optional[int]]:
    if not PID_FILE.exists():
        return None, None
    try:
        lines = PID_FILE.read_text().strip().splitlines()
        if len(lines) >= 2:
            pid = int(lines[0])
            port = int(lines[1])
            if pid == -1:
                is_jarvis, _ = check_jarvis_service(port)
                if is_jarvis:
                    return pid, port
            elif is_pid_alive(pid):
                return pid, port
    except Exception:
        pass
    return None, None

def start_server_daemon(port: int) -> bool:
    pid, active_port = get_running_server_info()
    if pid is not None:
        console.print(f"[bold #FFD700]J.A.R.V.I.S. server is already running with PID {pid} on port {active_port}.[/]")
        return True
    
    # Check if the port is in use
    is_jarvis, is_open = check_jarvis_service(port)
    if is_open:
        if is_jarvis:
            console.print(f"[bold yellow]A J.A.R.V.I.S. server is already running on port {port} but wasn't tracked by this PID file. Re-registering...[/]")
            PID_FILE.parent.mkdir(parents=True, exist_ok=True)
            PID_FILE.write_text(f"-1\n{port}\n")
            return True
        else:
            console.print(f"[bold red]Error: Port {port} is occupied by another service.[/]")
            return False

    console.print(f"[bold #00F0FF]⬡ Starting J.A.R.V.I.S. server daemon on port {port}...[/]")
    log_dir = get_data_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = open(log_dir / "server.log", "a")
    
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "jarvis.server.app:app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=log_file,
        stderr=log_file,
        start_new_session=True
    )
    
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(f"{proc.pid}\n{port}\n")
    
    for _ in range(30):
        time.sleep(0.5)
        is_jarvis_spawned, _ = check_jarvis_service(port)
        if is_jarvis_spawned:
            console.print(f"[bold green]✓ J.A.R.V.I.S. server daemon started successfully (PID {proc.pid}, port {port}).[/]")
            return True
            
    console.print(f"[bold red]❌ J.A.R.V.I.S. server failed to start within 15 seconds. Check logs at data/server.log[/]")
    try:
        proc.terminate()
        proc.wait(timeout=2.0)
    except Exception:
        pass
    if PID_FILE.exists():
        PID_FILE.unlink()
    return False

def stop_server_daemon() -> bool:
    pid, port = get_running_server_info()
    if pid is None:
        console.print("[yellow]J.A.R.V.I.S. server is not running (no active PID file).[/]")
        if PID_FILE.exists():
            PID_FILE.unlink()
        return False
        
    console.print(f"[bold #FFD700]Stopping J.A.R.V.I.S. server daemon (PID {pid})...[/]")
    
    if pid == -1:
        console.print("[yellow]PID is unregistered (-1). Clearing tracking file only.[/]")
        if PID_FILE.exists():
            PID_FILE.unlink()
        return True

    try:
        os.killpg(pid, signal.SIGTERM)
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
            
    for _ in range(10):
        time.sleep(0.5)
        if not is_pid_alive(pid):
            break
    else:
        console.print("[red]Server did not exit on SIGTERM. Escalating to SIGKILL...[/]")
        try:
            os.killpg(pid, signal.SIGKILL)
        except Exception:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
                
    if PID_FILE.exists():
        PID_FILE.unlink()
    console.print("[bold green]✓ J.A.R.V.I.S. server daemon stopped.[/]")
    return True

def status_server_daemon():
    pid, port = get_running_server_info()
    if pid is None:
        console.print("[bold red]J.A.R.V.I.S. Server Status: OFFLINE[/]")
        return
        
    is_jarvis, is_open = check_jarvis_service(port)
    if is_jarvis:
        console.print(Panel(
            f"[bold green]ONLINE[/]\n\n"
            f"[bold #FFD700]PID:[/] {pid}\n"
            f"[bold #FFD700]Port:[/] {port}\n"
            f"[bold #FFD700]URL:[/] http://localhost:{port}",
            title="J.A.R.V.I.S. Server Daemon Status",
            border_style="green"
        ))
    else:
        console.print(Panel(
            f"[bold yellow]STALE PID / UNRESPONSIVE[/]\n\n"
            f"[bold #FFD700]PID:[/] {pid}\n"
            f"[bold #FFD700]Port:[/] {port}\n"
            f"The server process is registered but health checks on port {port} are failing.",
            title="J.A.R.V.I.S. Server Daemon Status",
            border_style="yellow"
        ))

class JarvisTUI:
    def __init__(self):
        self.api_key = os.environ.get("NVIDIA_API_KEY")
        self.port = int(os.environ.get("JARVIS_PORT", 8008))
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
        info_table.add_row("[#00F0FF]⬡[/]", "ENDPOINT:", f"[white]http://localhost:{self.port}[/]")
        info_table.add_row("[#00F0FF]⬡[/]", "SESSION:", f"[white]{getattr(self, 'session_title', self.session_id)}[/]")
        
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
        model = getattr(self, "current_model", "house-party")
        agent = getattr(self, "active_agent_id", "jarvis")
        title = getattr(self, "session_title", self.session_id)
        if len(title) > 30:
            title = title[:27] + "..."
        return HTML(
            f" <b>Session:</b> {title} | "
            f"<b>Agent:</b> {agent.upper()} | "
            f"<b>Model:</b> {model} | "
            f"Type / for commands"
        )

    async def init(self):
        if not self.api_key:
            console.print("[bold #E63946]WARNING: NVIDIA_API_KEY environment variable is not set. API calls will fail.[/]")
            
        # 1. Check if server is running on the configured port or tracked by PID file.
        pid, active_port = get_running_server_info()
        if pid is not None:
            is_jarvis, is_open = check_jarvis_service(active_port)
            if is_jarvis:
                self.port = active_port
                self.external_server = True
                logger.info(f"Connected to running J.A.R.V.I.S. daemon on port {self.port} (PID {pid})")
                console.print(f"[bold green]✓ Connected to active J.A.R.V.I.S. server on port {self.port}.[/]")
            else:
                self.external_server = False
        else:
            is_jarvis, is_open = check_jarvis_service(self.port)
            if is_jarvis:
                self.external_server = True
                logger.info(f"Connected to running J.A.R.V.I.S. server on port {self.port}")
                console.print(f"[bold green]✓ Connected to active J.A.R.V.I.S. server on port {self.port}.[/]")
            else:
                self.external_server = False

        if not self.external_server:
            is_open = False
            _, is_open = check_jarvis_service(self.port)
            if is_open:
                old_port = self.port
                self.port = find_free_port(self.port)
                console.print(f"[bold #FFD700]⚠ Port {old_port} occupied by another service. Scanning for free port... Found {self.port}.[/]")
                
            console.print(f"[bold #00F0FF]⬡ Background API Server is offline. Starting service on port {self.port}...[/]")
            log_dir = get_data_dir()
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = open(log_dir / "server.log", "a")
            
            self.spawned_server = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "jarvis.server.app:app", "--host", "127.0.0.1", "--port", str(self.port)],
                stdout=log_file,
                stderr=log_file,
                start_new_session=True
            )
            
            PID_FILE.parent.mkdir(parents=True, exist_ok=True)
            PID_FILE.write_text(f"{self.spawned_server.pid}\n{self.port}\n")
            
            # Wait for server to accept connections
            for _ in range(30):
                await asyncio.sleep(0.5)
                is_jarvis_spawned, _ = check_jarvis_service(self.port)
                if is_jarvis_spawned:
                    console.print(f"[bold green]✓ Background API Server spawned successfully on port {self.port}.[/]\n")
                    break
            else:
                console.print(f"[bold red]❌ Failed to connect to spawned API server on port {self.port}. Verify logs at data/server.log[/]\n")
                if PID_FILE.exists():
                    PID_FILE.unlink()
                
        # Run diagnostics verification
        check_system_dependencies()

        # 2. Get active session or create a new one from the API server
        async with httpx.AsyncClient() as client:
            try:
                # Retrieve the session list to resume the most recent one
                res = await client.get(f"http://127.0.0.1:{self.port}/v1/sessions", timeout=5.0)
                res.raise_for_status()
                sessions_list = res.json()
                if sessions_list:
                    self.session_id = sessions_list[0]["session_id"]
                    self.current_model = sessions_list[0].get("model") or "house-party"
                    self.active_agent_id = sessions_list[0].get("agent_id") or "jarvis"
                    self.session_title = sessions_list[0].get("title") or self.session_id
                    console.print(f"[bold green]✓ Resuming previous dialogue session: {self.session_title} ({self.session_id})[/]\n")
                else:
                    res_new = await client.post(f"http://127.0.0.1:{self.port}/v1/sessions", timeout=5.0)
                    res_new.raise_for_status()
                    self.session_id = res_new.json()["session_id"]
                    self.current_model = "house-party"
                    self.active_agent_id = "jarvis"
                    self.session_title = self.session_id
                    console.print(f"[bold green]✓ Created new dialogue session: {self.session_id}[/]\n")
            except Exception as e:
                logger.error(f"Failed to resolve session on API server: {e}")
                console.print(f"[bold red]❌ Connection to API server failed:[/] {e}")
                self.session_id = "local_fallback"
                self.current_model = "house-party"
                self.active_agent_id = "jarvis"
                self.session_title = "Local Fallback"

        # Start background sse listener task
        self.in_turn = False
        self.sse_task = asyncio.create_task(self.sse_listener())

        # 3. Startup the subconscious routine engine (redirects routine requests to the server)
        async def _background_runner(prompt: str):
            async with httpx.AsyncClient() as client:
                try:
                    await client.post(
                        f"http://127.0.0.1:{self.port}/v1/sessions/{self.session_id}/chat",
                        json={"message": prompt, "client_id": "tui"},
                        timeout=5.0
                    )
                except Exception as e:
                    logger.error(f"Failed to submit subconscious routine: {e}")
                    
        self.subconscious = SubconsciousEngine(_background_runner)
        self.subconscious.start()

    def shutdown(self):
        """Cleans up the subconscious engine and kills the spawned server if active."""
        if hasattr(self, "sse_task"):
            self.sse_task.cancel()
            
        if hasattr(self, "subconscious"):
            self.subconscious.stop()
            
        if not getattr(self, "external_server", True) and self.spawned_server:
            console.print("\n[dim #FFD700]Shutting down background API server...[/]")
            try:
                os.killpg(self.spawned_server.pid, signal.SIGTERM)
                self.spawned_server.wait(timeout=3.0)
            except Exception:
                try:
                    self.spawned_server.terminate()
                    self.spawned_server.wait(timeout=3.0)
                except Exception:
                    pass
            if PID_FILE.exists():
                PID_FILE.unlink()
            console.print("[dim #FFD700]API Server Offline.[/]")
            
        console.print("\n[dim #FFD700]System Offline. ⚙[/]\n")

    async def sse_listener(self):
        """Listens to the active session stream and prints updates if not currently in a TUI-driven turn."""
        import httpx
        while True:
            if not self.session_id or self.session_id == "local_fallback":
                await asyncio.sleep(2.0)
                continue
                
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream(
                        "GET",
                        f"http://127.0.0.1:{self.port}/v1/sessions/{self.session_id}/stream?client_id=tui"
                    ) as response:
                        event_type = None
                        reasoning_text = ""
                        response_text = ""
                        
                        def cleanup_and_print():
                            nonlocal reasoning_text, response_text
                            if reasoning_text.strip():
                                console.print(Panel(reasoning_text.strip(), title="Thinking Processes", border_style="#FFD700", title_align="left"))
                                reasoning_text = ""
                            if response_text.strip():
                                console.print(Markdown(response_text))
                                response_text = ""

                        async for line in response.aiter_lines():
                            if self.in_turn:
                                continue
                                
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
                                    
                                if event_type == "text_chunk":
                                    text = data.get("text", "")
                                    if text:
                                        response_text += text
                                        
                                elif event_type == "reasoning_chunk":
                                    text = data.get("text", "")
                                    if text:
                                        reasoning_text += text
                                        
                                elif event_type == "tool_call_start":
                                    cleanup_and_print()
                                    name = data.get("name", "").upper()
                                    args = data.get("arguments", {})
                                    console.print(f"\n[bold #E63946]⚙ TOOL EXECUTION (Web UI):[/] [bold #FFD700]{name}[/]")
                                    if args:
                                        for k, v in args.items():
                                            v_str = str(v).replace("\n", " ")
                                            if len(v_str) > 150:
                                                v_str = v_str[:150] + "... (truncated)"
                                            console.print(f"  [bold #FFD700]▪ {k}:[/] [white]{v_str}[/]", highlight=False)
                                            
                                elif event_type == "tool_call_complete":
                                    cleanup_and_print()
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
                                    
                                elif event_type == "user_message":
                                    cleanup_and_print()
                                    text = data.get("text", "")
                                    console.print(f"[bold #FFD700]❯ [/]{text}")
                                    
                                elif event_type == "agent_changed":
                                    new_agent = data.get("agent_id", "jarvis")
                                    self.active_agent_id = new_agent
                                    console.print(f"\n[bold #00F0FF]⬡ ACTIVE AGENT SWITCHED TO:[/] [bold #FFD700]{new_agent.upper()}[/]")
                                    
                                elif event_type == "title_changed":
                                    new_title = data.get("title", "")
                                    if new_title:
                                        self.session_title = new_title
                                        console.print(f"\n[bold #00F0FF]⬡ SESSION TITLE SET TO:[/] [bold #FFD700]{new_title}[/]")
                                    
                                elif event_type == "turn_complete":
                                    cleanup_and_print()
                                    console.print()
            except Exception as e:
                logger.debug(f"SSE listener reconnection pending: {e}")
            await asyncio.sleep(2.0)

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
                    res = await client.post(f"http://127.0.0.1:{self.port}/v1/sessions", timeout=5.0)
                    self.session_id = res.json()["session_id"]
                    try:
                        session_details = await client.get(f"http://127.0.0.1:{self.port}/v1/sessions/{self.session_id}", timeout=5.0)
                        self.current_model = session_details.json().get("model") or "house-party"
                    except Exception:
                        self.current_model = "house-party"
                    console.print(f"[bold #FFD700]✓ Started new dialogue session: {self.session_id}[/]\n")
                except Exception as e:
                    console.print(f"[bold red]❌ Failed to start new session:[/] {e}\n")
            return True
        elif base == "/tasks":
            await print_tasks()
            return True
        elif base == "/skills":
            skills_tools = load_skills_from_dir(get_skills_dir())
            lines = ["[bold]Loaded Skill Modules:[/bold]"]
            for s in skills_tools:
                lines.append(f"  [bold cyan]▪[/] {s.name} - {s.description}")
            console.print(Panel("\n".join(lines), title="System Skills Matrix", border_style="#FFD700"))
            return True
        elif base == "/models":
            async with httpx.AsyncClient() as client:
                try:
                    res_models = await client.get(f"http://127.0.0.1:{self.port}/v1/models", timeout=5.0)
                    models = res_models.json()["models"]
                    
                    res_session = await client.get(f"http://127.0.0.1:{self.port}/v1/sessions/{self.session_id}", timeout=5.0)
                    current_model = res_session.json().get("model") or "house-party"
                    
                    lines = ["[bold]Stark Core Matrix:[/bold]"]
                    for i, m in enumerate(models):
                        prefix = "  "
                        if m == current_model:
                            prefix = "[bold cyan]⬡[/]"
                        
                        if m == "house-party":
                            lines.append(f"{prefix} {i+1}. {m} (Dynamic Multi-Model Protocol)")
                        else:
                            lines.append(f"{prefix} {i+1}. {m}")
                    lines.append("\n[dim]Usage: /model <index|name|house_party>[/dim]")
                    console.print(Panel("\n".join(lines), title="Stark Core Matrix Config", border_style="#FFD700"))
                except Exception as e:
                    console.print(f"[bold red]❌ Failed to retrieve models:[/] {e}\n")
            return True
        elif base == "/model":
            if len(parts) < 2:
                return await self.handle_slash("/models")
                
            arg = parts[1].strip().lower()
            async with httpx.AsyncClient() as client:
                try:
                    res_models = await client.get(f"http://127.0.0.1:{self.port}/v1/models", timeout=5.0)
                    models = res_models.json()["models"]
                    
                    matched_model = None
                    if arg in ("house_party", "houseparty", "house", "h", "dynamic", "d"):
                        matched_model = "house-party"
                    else:
                        try:
                            idx = int(arg) - 1
                            if 0 <= idx < len(models):
                                matched_model = models[idx]
                            else:
                                console.print("[bold #E63946]Invalid model index.[/bold #E63946]\n")
                                return True
                        except ValueError:
                            matched_model = next((m for m in models if arg in m.lower()), None)
                            
                    if not matched_model:
                        console.print(f"[bold #E63946]Model '{arg}' not found in matrix.[/bold #E63946]\n")
                        return True
                        
                    res_update = await client.post(
                        f"http://127.0.0.1:{self.port}/v1/sessions/{self.session_id}/model",
                        json={"model": matched_model},
                        timeout=5.0
                    )
                    if res_update.status_code == 200:
                        self.current_model = matched_model
                        console.print(f"[bold #FFD700]✓ Primary routing set to: {matched_model}[/bold #FFD700]\n")
                    else:
                        console.print(f"[bold red]❌ Failed to update model:[/] {res_update.text}\n")
                except Exception as e:
                    console.print(f"[bold red]❌ Connection error:[/] {e}\n")
            return True
        elif base in ("/subagents", "/agents", "/sub"):
            lines = [
                "[bold #00F0FF]F.R.I.D.A.Y. (Tactical HUD Assistant)[/]",
                "  [bold #FFD700]▪ Focus:[/] Desktop automation, window management, screen captures & execution.",
                "  [bold #FFD700]▪ Model:[/] nvidia/stepfun-ai/step-3.7-flash",
                "  [bold #FFD700]▪ Usage:[/] Ask J.A.R.V.I.S.: 'Ask Friday to take a screenshot' or 'Run command on Friday'.",
                "",
                "[bold #00F0FF]H.O.M.E.R. (Scholarly Research Intel)[/]",
                "  [bold #FFD700]▪ Focus:[/] Multi-engine web search, clean page structures, Playwright navigation & grounding.",
                "  [bold #FFD700]▪ Model:[/] nvidia/mistralai/mistral-large-3-675b-instruct-2512",
                "  [bold #FFD700]▪ Usage:[/] Ask J.A.R.V.I.S.: 'Ask Homer to search the web for...'.",
                "",
                "[bold #00F0FF]P.L.A.T.O. (Logical Strategy Consultant)[/]",
                "  [bold #FFD700]▪ Focus:[/] Deep reasoning, static code analysis, complex problem solving & drafting.",
                "  [bold #FFD700]▪ Model:[/] nvidia/deepseek-ai/deepseek-v4-pro",
                "  [bold #FFD700]▪ Usage:[/] Ask J.A.R.V.I.S.: 'Ask Plato to review my code in...'"
            ]
            console.print(Panel("\n".join(lines), title="Cognitive Sub-routines Matrix", border_style="#E63946"))
            return True
        elif base == "/switch":
            async with httpx.AsyncClient() as client:
                try:
                    res = await client.get(f"http://127.0.0.1:{self.port}/v1/sessions", timeout=5.0)
                    res.raise_for_status()
                    sessions = res.json()
                    
                    if len(parts) < 2:
                        lines = ["[bold]Existing Dialogue Sessions:[/bold]"]
                        for i, s in enumerate(sessions):
                            active_indicator = "  "
                            if s["session_id"] == self.session_id:
                                active_indicator = "[bold cyan]⬡[/]"
                            title = s.get("title") or s["session_id"]
                            agent = s.get("agent_id", "jarvis").upper()
                            model = s.get("model") or "house-party"
                            lines.append(f"{active_indicator} {i+1}. {title} [dim]({agent} | {model} | {s['session_id']})[/dim]")
                        lines.append("\n[dim]Usage: /switch <index|session_id>[/dim]")
                        console.print(Panel("\n".join(lines), title="Stark Dialogue Archive", border_style="#FFD700"))
                        return True
                    
                    arg = parts[1].strip()
                    matched_session = None
                    try:
                        idx = int(arg) - 1
                        if 0 <= idx < len(sessions):
                            matched_session = sessions[idx]
                        else:
                            console.print("[bold #E63946]Invalid session index.[/bold #E63946]\n")
                            return True
                    except ValueError:
                        matched_session = next((s for s in sessions if arg == s["session_id"]), None)
                        if not matched_session:
                            matched_session = next((s for s in sessions if s["session_id"].startswith(arg)), None)
                            
                    if not matched_session:
                        console.print(f"[bold #E63946]Session '{arg}' not found.[/bold #E63946]\n")
                        return True
                    
                    self.session_id = matched_session["session_id"]
                    self.current_model = matched_session.get("model") or "house-party"
                    self.active_agent_id = matched_session.get("agent_id") or "jarvis"
                    self.session_title = matched_session.get("title") or self.session_id
                    
                    if hasattr(self, "sse_task"):
                        self.sse_task.cancel()
                    self.sse_task = asyncio.create_task(self.sse_listener())
                    
                    console.print(f"[bold #FFD700]✓ Switched to session: {self.session_title} ({self.session_id})[/bold #FFD700]\n")
                except Exception as e:
                    console.print(f"[bold red]❌ Failed to switch session:[/] {e}\n")
            return True
        elif base == "/agent":
            if len(parts) < 2:
                console.print(f"[bold #FFD700]Active Session Agent:[/] [bold cyan]{getattr(self, 'active_agent_id', 'jarvis').upper()}[/bold cyan]")
                console.print("[dim]Usage: /agent <jarvis|friday|homer|plato>[/dim]\n")
                return True
            
            agent_id = parts[1].strip().lower()
            if agent_id not in ("jarvis", "friday", "homer", "plato"):
                console.print(f"[bold #E63946]Invalid agent ID '{agent_id}'. Must be one of: jarvis, friday, homer, plato.[/bold #E63946]\n")
                return True
                
            async with httpx.AsyncClient() as client:
                try:
                    res = await client.post(
                        f"http://127.0.0.1:{self.port}/v1/sessions/{self.session_id}/switch-agent",
                        json={"agent_id": agent_id},
                        timeout=5.0
                    )
                    res.raise_for_status()
                    self.active_agent_id = agent_id
                    console.print(f"[bold #FFD700]✓ Active agent set to: {agent_id.upper()}[/bold #FFD700]\n")
                except Exception as e:
                    console.print(f"[bold red]❌ Failed to switch agent:[/] {e}\n")
            return True
        elif base == "/voicemode":
            async with httpx.AsyncClient() as client:
                try:
                    if len(parts) < 2:
                        res = await client.get(f"http://127.0.0.1:{self.port}/v1/voice/status", timeout=5.0)
                        res.raise_for_status()
                        status = res.json()
                        state = "ON" if status.get("enabled") else "OFF"
                        voice = status.get("voice") or "unresolved"
                        gender = status.get("gender") or "unknown"
                        lines = [
                            f"[bold]Voice Mode:[/bold] {state}",
                            f"[bold]Voice:[/bold] {voice} ({gender})",
                            f"[bold]TTS:[/bold] {'available' if status.get('tts_available') else 'unavailable'}",
                            f"[bold]STT:[/bold] {'available' if status.get('stt_available') else 'unavailable'}",
                        ]
                        warning = status.get("persona_warning")
                        if warning:
                            lines.append(f"[bold #E63946]Warning:[/bold #E63946] {warning}")
                        if status.get("error"):
                            lines.append(f"[dim]Error: {status['error']}[/dim]")
                        lines.append("\n[dim]Usage: /voicemode on|off[/dim]")
                        console.print(Panel("\n".join(lines), title="Voice Mode Status", border_style="#FFD700"))
                        return True

                    arg = parts[1].strip().lower()
                    if arg in ("on", "true", "1", "yes", "enable"):
                        enabled = True
                    elif arg in ("off", "false", "0", "no", "disable"):
                        enabled = False
                    else:
                        console.print("[bold #E63946]Usage: /voicemode [on|off][/bold #E63946]\n")
                        return True

                    res = await client.post(
                        f"http://127.0.0.1:{self.port}/v1/voice/mode",
                        json={"enabled": enabled},
                        timeout=5.0,
                    )
                    if res.status_code == 503:
                        console.print(f"[bold #E63946]Voice services unavailable:[/] {res.text}\n")
                        return True
                    res.raise_for_status()
                    if enabled:
                        console.print(
                            "[bold #FFD700]✓ Voice mode enabled.[/] "
                            "Jarvis will speak in a male English butler voice; "
                            "use the Web HUD microphone to dictate.\n"
                        )
                    else:
                        console.print("[bold #FFD700]✓ Voice mode disabled.[/]\n")
                except Exception as e:
                    console.print(f"[bold red]❌ Failed to update voice mode:[/] {e}\n")
            return True
        elif base == "/exit":
            self.shutdown()
            sys.exit(0)
        return False

    async def run_loop(self):
        self.print_splash()
        
        history_path = get_data_dir() / "pt_history.txt"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        
        from prompt_toolkit.completion import merge_completers
        session_pt = PromptSession(
            completer=merge_completers([SlashCompleter(), FileMentionCompleter()]),
            auto_suggest=AutoSuggestFromHistory(),
            style=PT_STYLE,
            key_bindings=self.kb,
            bottom_toolbar=self._bottom_toolbar,
            complete_while_typing=True,
            enable_history_search=True,
            history=FileHistory(str(history_path)),
            multiline=True
        )
        
        with patch_stdout(raw=True):
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
        import re
        
        # Set turn flag to suspend remote sse listener prints
        self.in_turn = True
        
        try:
            # Extract and upload @ mentions
            mentions = re.findall(r'@([^\s]+)', prompt)
            uploaded_files = []
            cleaned_prompt = prompt
            
            async with httpx.AsyncClient() as client:
                for mention in mentions:
                    file_path = Path(mention)
                    if file_path.exists() and file_path.is_file():
                        try:
                            contents = file_path.read_bytes()
                            filename = file_path.name
                            files_data = {"file": (filename, contents)}
                            upload_res = await client.post(
                                f"http://127.0.0.1:{self.port}/v1/sessions/{self.session_id}/files",
                                files=files_data,
                                timeout=10.0
                            )
                            if upload_res.status_code == 200:
                                file_info = upload_res.json()
                                uploaded_files.append(file_info)
                                cleaned_prompt = cleaned_prompt.replace(f"@{mention}", filename)
                            else:
                                logger.error(f"Failed to upload {mention}: {upload_res.text}")
                        except Exception as upload_err:
                            logger.error(f"Error uploading file {mention}: {upload_err}")
            
            # Clear user prompt line and reprint cleaned version
            try:
                num_lines = len(prompt.split('\n'))
                sys.stdout.flush()
                await asyncio.sleep(0.02)
                sys.__stdout__.write(f"\033[F\033[K" * num_lines)
                sys.__stdout__.flush()
                console.print(f"[bold #FFD700]❯ [/]{cleaned_prompt}")
            except Exception:
                pass

            # 1. Post request to submit chat input
            async with httpx.AsyncClient() as client:
                try:
                    payload = {"message": cleaned_prompt, "client_id": "tui"}
                    if uploaded_files:
                        payload["files"] = uploaded_files
                        
                    chat_res = await client.post(
                        f"http://127.0.0.1:{self.port}/v1/sessions/{self.session_id}/chat",
                        json=payload,
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
            
            def cleanup_live_and_print_accumulators():
                nonlocal live, reasoning_text, response_text
                if live:
                    live.stop()
                    live = None
                if reasoning_text.strip():
                    console.print(Panel(reasoning_text.strip(), title="Thinking Processes", border_style="#FFD700", title_align="left"))
                    reasoning_text = ""
                if response_text.strip():
                    console.print(Markdown(response_text))
                    response_text = ""
 
            async with httpx.AsyncClient() as client:
                try:
                    async with client.stream(
                        "GET", 
                        f"http://127.0.0.1:{self.port}/v1/sessions/{self.session_id}/stream", 
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
                                            live = Live(Group(), refresh_per_second=15, console=raw_console, transient=True)
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
                                            live = Live(Group(), refresh_per_second=15, console=raw_console, transient=True)
                                            live.start()
                                        reasoning_text += text
                                        
                                        renderables = []
                                        if reasoning_text:
                                            renderables.append(Panel(reasoning_text, title="Thinking Processes", border_style="#FFD700", title_align="left"))
                                        if response_text:
                                            renderables.append(Markdown(response_text))
                                        live.update(Group(*renderables))
                                        
                                elif event_type == "tool_call_start":
                                    cleanup_live_and_print_accumulators()
                                        
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
                                    cleanup_live_and_print_accumulators()
                                        
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
                                    
                                elif event_type == "agent_changed":
                                    new_agent = data.get("agent_id", "jarvis")
                                    self.active_agent_id = new_agent
                                    console.print(f"\n[bold #00F0FF]⬡ ACTIVE AGENT SWITCHED TO:[/] [bold #FFD700]{new_agent.upper()}[/]")
                                    
                                elif event_type == "title_changed":
                                    new_title = data.get("title", "")
                                    if new_title:
                                        self.session_title = new_title
                                        console.print(f"\n[bold #00F0FF]⬡ SESSION TITLE SET TO:[/] [bold #FFD700]{new_title}[/]")

                                elif event_type == "turn_complete":
                                    break
                except Exception as e:
                    console.print(f"\n[bold #E63946]Error during SSE streaming:[/] {e}")
                finally:
                    cleanup_live_and_print_accumulators()
                    console.print() # separating line
        finally:
            self.in_turn = False

async def main():
    args = sys.argv[1:]
    
    if len(args) >= 1 and args[0] == "server":
        if len(args) < 2:
            console.print("[bold red]Error: Specify server command (start, stop, status).[/]")
            console.print("Usage: jarvis server start [--port PORT] | stop | status")
            sys.exit(1)
            
        cmd = args[1].lower()
        if cmd == "start":
            port = int(os.environ.get("JARVIS_PORT", 8008))
            if "--port" in args:
                idx = args.index("--port")
                if idx + 1 < len(args):
                    port = int(args[idx + 1])
            elif "-p" in args:
                idx = args.index("-p")
                if idx + 1 < len(args):
                    port = int(args[idx + 1])
            
            success = start_server_daemon(port)
            sys.exit(0 if success else 1)
            
        elif cmd == "stop":
            success = stop_server_daemon()
            sys.exit(0 if success else 1)
            
        elif cmd == "status":
            status_server_daemon()
            sys.exit(0)
            
        else:
            console.print(f"[bold red]Error: Unknown server command '{cmd}'.[/]")
            console.print("Usage: jarvis server start [--port PORT] | stop | status")
            sys.exit(1)
            
    tui = JarvisTUI()
    await tui.init()
    await tui.run_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
