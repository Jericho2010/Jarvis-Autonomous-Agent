import os
import sys
import asyncio
import logging
import subprocess
import signal
from pathlib import Path
from typing import Any, List, Optional
import httpx

from dotenv import load_dotenv
from rich.console import Console, Group
from rich.panel import Panel
from rich.markdown import Markdown
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
import contextlib
import warnings
from prompt_toolkit.patch_stdout import patch_stdout

from jarvis.config.paths import (
    get_data_dir,
    get_env_file,
)
from jarvis.core.system_deps import check_system_dependencies

# Load env from root
load_dotenv(get_env_file())

from jarvis.skills.skill_forge import load_skills_from_dir
from jarvis.evolution.subconscious import BackgroundRoutineEngine

# New split-off modules
from jarvis.completers import SlashCompleter, FileMentionCompleter
from jarvis.splash import PT_STYLE, render_splash
from jarvis.server_control import (
    PID_FILE,
    get_running_server_info,
    start_server_daemon,
    stop_server_daemon,
    status_server_daemon,
    check_jarvis_service,
    find_free_port,
    is_pid_alive,
)
from jarvis.slash_commands import handle_slash_command

def _load_skills_silent(path):
    try:
        with open(os.devnull, 'w') as devnull:
            with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull), warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return load_skills_from_dir(path)
    except Exception:
        logger.exception("Failed to load skills from %s", path)
        return []

console = Console()
raw_console = Console(file=sys.__stdout__)
logging.basicConfig(
    filename=str(get_data_dir() / "jarvis_client.log"),
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("jarvis.cli_client")


class JarvisTUI:
    def __init__(self):
        self.session_id = None
        self.session_title = None
        self.current_model = "house-party"
        self.active_agent_id = "jarvis"
        self.port = int(os.environ.get("JARVIS_PORT", 8008))
        self.spawned_server = None
        self.external_server = False
        self.in_turn = False
        self.turn_complete_event = asyncio.Event()
        self.kb = KeyBindings()
        self._setup_bindings()

    def _setup_bindings(self):
        @self.kb.add("c-c")
        def _interrupt(event):
            event.current_buffer.reset()

        @self.kb.add("tab")
        def _indent_or_complete(event):
            buff = event.current_buffer
            if buff.complete_state:
                buff.complete_next()
            else:
                buff.start_completion(select_first=False)

        @self.kb.add("/")
        def _slash_complete(event):
            event.current_buffer.insert_text("/")
            event.current_buffer.start_completion(select_first=False)

    def print_splash(self):
        render_splash(self.port, self.session_id, self.session_title)

    def set_session(self, session_id: str, title: Optional[str] = None):
        """Re-keys the active session and spawns a fresh SSE stream subscription."""
        self.session_id = session_id
        self.session_title = title or session_id
        if hasattr(self, "sse_task") and self.sse_task:
            self.sse_task.cancel()
        self.sse_task = asyncio.create_task(self.sse_listener())

    def _bottom_toolbar(self):
        agent = self.active_agent_id.upper()
        model = self.current_model
        session = self.session_title or self.session_id or "Local Fallback"
        
        return HTML(
            f"<style bg='ansired' fg='ansiyellow'><b> JARVIS HUD </b></style>"
            f"<style bg='#4A0000' fg='#FFD700'> | <b>Agent:</b> {agent} </style>"
            f"<style bg='#4A0000' fg='#FFD700'> | <b>Core:</b> {model} </style>"
            f"<style bg='#4A0000' fg='#FFD700'> | <b>Session:</b> {session} </style>"
            f"<style bg='#4A0000' fg='#FFD700'> [Ctrl+C: Clear | Tab: Complete] </style>"
        )

    async def init(self):
        # 1. Verify system dependencies
        check_system_dependencies(console)

        # 2. Setup server connection daemon
        pid, active_port = get_running_server_info()
        if pid is not None:
            self.port = active_port
            self.external_server = True
            console.print(f"[bold green]✓ Connected to active daemon server (PID {pid}, port {self.port}).[/]")
        else:
            is_jarvis, is_open = check_jarvis_service(self.port)
            if is_open:
                if is_jarvis:
                    self.external_server = True
                    console.print(f"[bold green]✓ Reconnected to active server on port {self.port}.[/]")
                else:
                    free_port = find_free_port(self.port + 1)
                    console.print(f"[yellow]Port {self.port} occupied. Swapping matrix router to port {free_port}...[/]")
                    self.port = free_port
            
            if not self.external_server:
                success = start_server_daemon(self.port)
                if not success:
                    console.print("[bold red]FATAL: J.A.R.V.I.S. Core server could not initialize. Falling back to local state.[/]")
                    self.session_id = "local_fallback"
                    return

        # Join the same session the Web HUD would (latest with messages), or create one.
        async with httpx.AsyncClient() as client:
            try:
                sessions_res = await client.get(f"http://127.0.0.1:{self.port}/v1/sessions", timeout=5.0)
                sessions_res.raise_for_status()
                sessions = sessions_res.json()
                if sessions:
                    session_id = sessions[0]["session_id"]
                    session_title = sessions[0].get("title") or session_id
                    self.current_model = sessions[0].get("model") or "house-party"
                else:
                    res = await client.post(
                        f"http://127.0.0.1:{self.port}/v1/sessions", json={}, timeout=5.0
                    )
                    res.raise_for_status()
                    session_id = res.json()["session_id"]
                    session_title = session_id
                    self.current_model = "house-party"

                try:
                    session_details = await client.get(
                        f"http://127.0.0.1:{self.port}/v1/sessions/{session_id}", timeout=5.0
                    )
                    self.current_model = session_details.json().get("model") or self.current_model
                    if session_details.json().get("title"):
                        session_title = session_details.json()["title"]
                except Exception:
                    pass
                self.set_session(session_id, session_title)
            except Exception as e:
                console.print(f"[bold red]❌ Failed to initialize dialogue session:[/] {e}")
                self.session_id = "local_fallback"

        # 3. Startup the subconscious routine engine
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
                    
        self.subconscious = BackgroundRoutineEngine(_background_runner)
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

    async def play_voice_reply(self, text: str) -> None:
        """Fetch TTS audio from the API and play it on the local system."""
        if not text or not text.strip():
            return
        import tempfile
        import shutil

        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    f"http://127.0.0.1:{self.port}/v1/voice/tts",
                    json={"text": text},
                    timeout=60.0,
                )
                if res.status_code != 200:
                    logger.debug("TTS playback skipped: HTTP %s", res.status_code)
                    return
                wav_bytes = res.content
        except Exception as exc:
            logger.debug("TTS playback request failed: %s", exc)
            return

        player = shutil.which("aplay") or shutil.which("paplay")
        if not player:
            console.print("[dim #FFD700]Voice reply synthesized — install aplay or paplay for TUI audio.[/]")
            return

        wav_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(wav_bytes)
                wav_path = tmp.name
            subprocess.run([player, wav_path], check=False, capture_output=True)
        finally:
            if wav_path:
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass

    def _cleanup_live_and_print(self):
        """Utility to close any open rich Live rendering display and print accumulated text/reasoning."""
        if hasattr(self, "live") and self.live:
            try:
                self.live.stop()
            except Exception:
                pass
            self.live = None
        if hasattr(self, "reasoning_text") and self.reasoning_text.strip():
            console.print(Panel(self.reasoning_text.strip(), title="Thinking Processes", border_style="#FFD700", title_align="left"))
            self.reasoning_text = ""
        if hasattr(self, "response_text") and self.response_text.strip():
            console.print(Markdown(self.response_text))
            self.response_text = ""

    async def sse_listener(self):
        """Unified, long-lived background reader of the session event stream."""
        self.reasoning_text = ""
        self.response_text = ""
        self.live = None

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
                                    
                                if event_type == "text_chunk":
                                    text = data.get("text", "")
                                    if text:
                                        if not self.live:
                                            from rich.live import Live
                                            self.live = Live(Group(), refresh_per_second=15, console=raw_console, transient=True)
                                            self.live.start()
                                        self.response_text += text
                                        
                                        renderables = []
                                        if self.reasoning_text:
                                            renderables.append(Panel(self.reasoning_text, title="Thinking Processes", border_style="#FFD700", title_align="left"))
                                        if self.response_text:
                                            renderables.append(Markdown(self.response_text))
                                        self.live.update(Group(*renderables))
                                        
                                elif event_type == "reasoning_chunk":
                                    text = data.get("text", "")
                                    if text:
                                        if not self.live:
                                            from rich.live import Live
                                            self.live = Live(Group(), refresh_per_second=15, console=raw_console, transient=True)
                                            self.live.start()
                                        self.reasoning_text += text
                                        
                                        renderables = []
                                        if self.reasoning_text:
                                            renderables.append(Panel(self.reasoning_text, title="Thinking Processes", border_style="#FFD700", title_align="left"))
                                        if self.response_text:
                                            renderables.append(Markdown(self.response_text))
                                        self.live.update(Group(*renderables))
                                        
                                elif event_type == "tool_call_start":
                                    self._cleanup_live_and_print()
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
                                    self._cleanup_live_and_print()
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
                                    self._cleanup_live_and_print()
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
 
                                elif event_type == "approval_required":
                                    self._cleanup_live_and_print()
                                    tool_name = data.get("function_name", "desktop action")
                                    console.print(
                                        Panel(
                                            f"Tool: {tool_name}\nApprove or reject in the Web HUD.",
                                            title="[bold #FFD700]Desktop Action Pending Approval[/]",
                                            border_style="#FFD700",
                                        )
                                    )
 
                                elif event_type == "voice_ready":
                                    self._cleanup_live_and_print()
                                    spoken = data.get("text", "")
                                    if spoken:
                                        asyncio.create_task(self.play_voice_reply(spoken))
                                    
                                elif event_type == "turn_complete":
                                    self._cleanup_live_and_print()
                                    console.print()
                                    self.turn_complete_event.set()
            except Exception as e:
                logger.debug(f"SSE listener reconnection pending: {e}")
                self.turn_complete_event.set()
            await asyncio.sleep(2.0)

    async def handle_slash(self, cmd: str) -> bool:
        return await handle_slash_command(self, cmd)

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
            multiline=False
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
        
        self.in_turn = True
        
        try:
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
            
            try:
                num_lines = len(prompt.split('\n'))
                sys.stdout.flush()
                await asyncio.sleep(0.02)
                sys.__stdout__.write(f"\033[F\033[K" * num_lines)
                sys.__stdout__.flush()
                console.print(f"[bold #FFD700]❯ [/]{cleaned_prompt}")
            except Exception:
                pass

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
            
            try:
                await self.turn_complete_event.wait()
            except asyncio.sleep:  # standard sleep/cancelled placeholder
                pass
            except asyncio.CancelledError:
                pass
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
