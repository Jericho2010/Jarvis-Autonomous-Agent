import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Any, List, Optional

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

# Load env from root
load_dotenv(Path("/home/shaun/jarvis/.env"))

from jarvis.memory.memory_manager import MemoryManager
from jarvis.core.agent import create_jarvis_agent, DEFAULT_SYSTEM_PROMPT
from jarvis.skills.skill_forge import load_skills_from_dir, forge_skill
from jarvis.evolution.subconscious import SubconsciousEngine
from agent_framework._types import Message
import contextlib
import warnings

def _load_skills_silent(path):
    with open(os.devnull, 'w') as devnull:
        with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return load_skills_from_dir(path)

console = Console()
logging.basicConfig(
    filename="/home/shaun/jarvis/data/jarvis.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("jarvis.cli")

SLASH_COMMANDS = {
    "/help": "Show this help manual",
    "/new": "Start a fresh dialogue session",
    "/tasks": "Show the Jarvis implementation task list",
    "/skills": "List all loaded skill modules",
    "/model": "List or set the primary Stark Core Matrix model",
    "/cron": "Register a subconscious routine: /cron <seconds> \"<prompt>\"",
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
    task_path = Path("/home/shaun/.gemini/antigravity-ide/brain/bb5fbcbe-90fd-4c47-aa08-f0105ba53197/task.md")
    if task_path.exists():
        console.print(Panel(task_path.read_text(), title="Jarvis Implementation Tasks", border_style="#FFD700"))
    else:
        console.print("[yellow]No tasks file found at active path.[/]")

class JarvisTUI:
    def __init__(self):
        self.api_key = os.environ.get("NVIDIA_API_KEY")
        db_path = os.environ.get("JARVIS_DB_PATH", "/home/shaun/jarvis/data/jarvis.db")
        self.memory = MemoryManager(Path(db_path))
        self.session_id = f"session_{int(asyncio.get_event_loop().time())}"
        self.agent = None
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
        primary = "Neural Uplink: Dynamic Matrix"
        if self.agent and hasattr(self.agent, "client") and self.agent.client.primary_model != "house_party":
            primary = self.agent.client.primary_model

        # Multi-line Unicode Arc Reactor Graphics
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
        info_table.add_row("[#00F0FF]⬡[/]", "STATUS:", "[bold green]ONLINE[/]")
        info_table.add_row("[#00F0FF]⬡[/]", "HOST CORE:", "[bold #FFD700]NVIDIA NIM APIs[/]")
        info_table.add_row("[#00F0FF]⬡[/]", "ROUTING:", f"[bold #FFD700]{primary}[/]")
        info_table.add_row("[#00F0FF]⬡[/]", "FALLBACK:", "[white]Redundancy: House Party Protocol[/]")
        info_table.add_row("[#00F0FF]⬡[/]", "MEMORY DB:", f"[white]SQLite ({self.session_id})[/]")
        
        splash_table = Table.grid(padding=(0, 4))
        splash_table.add_row(reactor_graphic, info_table)

        console.print(ASCII_ART)
        console.print(Panel(
            Align.center(splash_table),
            title="[bold #FFD700]MARK XLVII - COGNITIVE INTERFACE[/]",
            border_style="#E63946",
            padding=(1, 2)
        ))
        console.print("Type [bold #FFD700]/help[/] for command manual. Press [bold cyan]Enter[/] to submit, [bold cyan]Alt+Enter[/] for multiline.\n")


    def _bottom_toolbar(self):
        primary = "house_party"
        if self.agent and hasattr(self.agent, "client"):
            primary = self.agent.client.primary_model
            
        return HTML(
            f" <b>Session:</b> {self.session_id} | "
            f"<b>Primary:</b> {primary} | "
            f"<b>Endpoint:</b> NIM | "
            f"Type / for commands"
        )

    async def init(self):
        await self.memory.init_db()
        if not self.api_key:
            console.print("[bold #E63946]WARNING: NVIDIA_API_KEY environment variable is not set. API calls will fail.[/]")
        
        # Load local skills
        skills_tools = _load_skills_silent(Path("/home/shaun/jarvis/skills"))
        
        # Register forge_skill tool
        self.all_tools = [forge_skill] + skills_tools
        
        # Inject user profile and dynamic Edwin soul into system instructions
        profile = await self.memory.build_profile_prompt()
        
        soul_body = ""
        soul_file = Path("/home/shaun/jarvis/skills/jarvis_soul/SKILL.md")
        if soul_file.exists():
            try:
                content = soul_file.read_text(encoding="utf-8")
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        soul_body = parts[2].strip()
                else:
                    soul_body = content.strip()
            except Exception as soul_err:
                logger.error(f"Failed to parse Edwin soul instructions: {soul_err}")
                
        self.custom_instructions = f"{DEFAULT_SYSTEM_PROMPT}"
        if soul_body:
            self.custom_instructions += f"\n\n# ACTIVE PERSONA PROFILE\n{soul_body}"
        self.custom_instructions += f"\n\n{profile}"
        
        self.agent = create_jarvis_agent(
            api_key=self.api_key or "",
            instructions_override=self.custom_instructions,
            tools=self.all_tools
        )
        
        # Log session startup
        await self.memory.create_session(
            session_id=self.session_id,
            model="house-party",
            system_prompt=self.custom_instructions
        )
        
        async def _background_runner(prompt: str):
            msgs = [Message(role="user", contents=[prompt])]
            response = await self.agent.run(messages=msgs)
            await self.memory.add_message(self.session_id, "user", f"[Routine] {prompt}")
            await self.memory.add_message(self.session_id, "assistant", f"[Routine Complete]\n{response.text}")
            
            import subprocess
            try:
                subprocess.run(['notify-send', '-a', 'JARVIS', 'Subconscious Routine Complete', prompt], check=False)
            except Exception:
                pass
                
            console.print(f"\n[#00E5FF]⬡ Subconscious:[/] Routine completed. Check memory or /tasks for output.")

        self.subconscious = SubconsciousEngine(_background_runner)
        self.subconscious.start()

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
            self.session_id = f"session_{int(asyncio.get_event_loop().time())}"
            await self.init()
            console.print(f"[bold #FFD700]✓ Started new dialogue session: {self.session_id}[/]\n")
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
        elif base == "/model":
            client = getattr(self.agent, "client", None)
            if not client:
                console.print("[red]Agent client not initialized.[/]")
                return True
                
            basket = client.model_basket
            
            if len(parts) == 1:
                # Just list
                lines = ["[bold]Stark Core Matrix:[/bold]"]
                for i, m in enumerate(basket):
                    prefix = "  "
                    if client.primary_model == m:
                        prefix = "[bold cyan]⬡[/]"
                    lines.append(f"{prefix} {i+1}. {m}")
                
                dyn_prefix = "[bold cyan]⬡[/]" if client.primary_model == "house_party" else "  "
                lines.append(f"{dyn_prefix} H. house_party (Dynamic Multi-Model Protocol)")
                lines.append("\n[dim]Usage: /model <index|name|house_party>[/dim]")
                console.print(Panel("\n".join(lines), title="Stark Core Matrix Config", border_style="#FFD700"))
                return True
            else:
                arg = parts[1].strip().lower()
                if arg in ("house_party", "houseparty", "house", "h", "dynamic", "d"):
                    client.primary_model = "house_party"
                    console.print("[bold #FFD700]✓ Primary routing set to: house_party (Dynamic Multi-Model Protocol)[/bold #FFD700]\n")
                else:
                    try:
                        idx = int(arg) - 1
                        if 0 <= idx < len(basket):
                            client.primary_model = basket[idx]
                            console.print(f"[bold #FFD700]✓ Primary model set to: {basket[idx]}[/bold #FFD700]\n")
                        else:
                            console.print("[bold #E63946]Invalid model index.[/bold #E63946]")
                    except ValueError:
                        # try matching by name
                        matched = next((m for m in basket if arg in m.lower()), None)
                        if matched:
                            client.primary_model = matched
                            console.print(f"[bold #FFD700]✓ Primary model set to: {matched}[/bold #FFD700]\n")
                        else:
                            console.print(f"[bold #E63946]Model '{arg}' not found in matrix.[/bold #E63946]")
            return True
        elif base == "/cron":
            try:
                args = parts[1].split(' ', 1)
                interval = int(args[0])
                prompt = args[1].strip('"\'')
                self.subconscious.add_routine(interval, prompt, f"Task_{interval}s")
            except Exception:
                console.print("[red]Usage: /cron <seconds> \"<prompt>\"[/red]")
            return True
        elif base == "/exit":
            if hasattr(self, "subconscious"):
                self.subconscious.stop()
            console.print("\n[dim #FFD700]System Offline. ⚙[/]\n")
            sys.exit(0)
        return False

    async def run_loop(self):
        self.print_splash()
        
        # Set up prompt session
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
                
                # Execute agent turn
                await self.execute_turn(user_input)
                
            except KeyboardInterrupt:
                console.print("\n[bold #E63946]⚡ Interrupted[/]\n")
                continue
            except EOFError:
                console.print("\n[dim #FFD700]System Offline. ⚙[/]\n")
                break
            except Exception as e:
                console.print(f"[bold #E63946]System Error:[/] {e}")
                logger.exception("Error in main loop")

    async def execute_turn(self, prompt: str):
        # Store user message
        await self.memory.add_message(self.session_id, "user", prompt)
        
        # Fetch full session history to pass to agent run
        history_msgs = await self.memory.get_session_history(self.session_id)
        
        # Convert simple history dicts to agent_framework Messages
        agent_msgs = []
        for m in history_msgs:
            agent_msgs.append(Message(role=m["role"], contents=[m["content"] or ""]))
            
        from rich.live import Live
        
        live = None
        raw_buffer = ""
        reasoning_text = ""
        response_text = ""
        accumulated_text = ""
        
        active_task = None
        
        async def run_agent():
            nonlocal live, raw_buffer, reasoning_text, response_text, accumulated_text
            try:
                # We start streaming the response
                async for chunk in self.agent.run(messages=agent_msgs, stream=True):
                    has_tool_call = any(c.type == "function_call" for c in chunk.contents)
                    
                    if chunk.text:
                        if not live:
                            live = Live(Group(), refresh_per_second=15, console=console)
                            live.start()
                            
                        raw_buffer += chunk.text
                        
                        # Accumulative state-free reasoning parsing
                        if "<think>" in raw_buffer:
                            if "</think>" in raw_buffer:
                                parts = raw_buffer.split("<think>", 1)
                                before_think = parts[0]
                                think_and_after = parts[1].split("</think>", 1)
                                reasoning_text = think_and_after[0].strip()
                                response_text = before_think + think_and_after[1]
                            else:
                                parts = raw_buffer.split("<think>", 1)
                                reasoning_text = parts[1].strip()
                                response_text = parts[0]
                        else:
                            reasoning_text = ""
                            response_text = raw_buffer
                            
                        # Update render group
                        renderables = []
                        if reasoning_text:
                            renderables.append(Panel(reasoning_text, title="Thinking Processes", border_style="#FFD700", title_align="left"))
                        if response_text:
                            renderables.append(Markdown(response_text))
                            
                        live.update(Group(*renderables))
                        
                    if has_tool_call:
                        if live:
                            live.stop()
                            live = None
                        if response_text.strip():
                            console.print(Markdown(response_text))
                        if reasoning_text:
                            accumulated_text += f"<think>\n{reasoning_text}\n</think>\n"
                        accumulated_text += response_text
                        raw_buffer = ""
                        reasoning_text = ""
                        response_text = ""
                        
            except asyncio.CancelledError:
                console.print("\n[bold #E63946]⚡ Interrupted[/]\n")
                # Ensure we store the interruption in memory
                if reasoning_text:
                    accumulated_text += f"<think>\n{reasoning_text}\n</think>\n"
                accumulated_text += response_text + "\n\n[Generation Interrupted by User]"
                
                if accumulated_text.strip():
                    await self.memory.add_message(
                        session_id=self.session_id,
                        role="assistant",
                        content=accumulated_text
                    )
            except Exception as ex:
                console.print(f"\n[bold #E63946]Error during response generation:[/] {ex}")
                logger.exception("Error in execute_turn run_agent")
            finally:
                if live:
                    live.stop()
                    live = None
                
                # Store agent turn response
                if reasoning_text:
                    accumulated_text += f"<think>\n{reasoning_text}\n</think>\n"
                accumulated_text += response_text
                
                if accumulated_text.strip():
                    await self.memory.add_message(
                        session_id=self.session_id,
                        role="assistant",
                        content=accumulated_text
                    )
                console.print() # separating line
                
        # Start executing
        active_task = asyncio.create_task(run_agent())
        try:
            await active_task
        except KeyboardInterrupt:
            active_task.cancel()
            await active_task
            console.print("\n[bold #E63946]⚡ Interrupted[/]\n")

async def main():
    tui = JarvisTUI()
    await tui.init()
    await tui.run_loop()

if __name__ == "__main__":
    asyncio.run(main())
