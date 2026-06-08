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

# Load env from root
load_dotenv(Path("/home/shaun/jarvis/.env"))

from jarvis.memory.memory_manager import MemoryManager
from jarvis.core.agent import create_jarvis_agent, DEFAULT_FALLBACK_LADDER
from jarvis.skills.skill_forge import load_skills_from_dir, forge_skill

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
    "/models": "List Trinity Council fallback models",
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

PT_STYLE = Style.from_dict({
    "prompt": "bold cyan",
    "bottom-toolbar": "bg:#1e1e24 #abb2bf",
    "completion-menu.completion": "bg:#282c34 #abb2bf",
    "completion-menu.completion.current": "bg:#61afef #282c34 bold",
    "completion-menu.meta.completion": "bg:#282c34 #abb2bf",
    "completion-menu.meta.completion.current": "bg:#61afef #282c34",
})

ASCII_ART = r"""[bold cyan]
      _   _   ___ __   __ ___  ___ 
   _ | | /_\ | _ \\\\ \\\\ / // __|/ __|
  | || |/ _ \\\\|   / \\\\ V / \\\\__ \\\\__ \\\\
   \\\\__//_/ \\\\_\\\\_|_\  \\\\_/  |___/|___/
[/]"""

def print_splash():
    console.print(ASCII_ART)
    console.print(Rule("[bold]Jarvis System Terminal[/]", style="cyan"))
    console.print(
        Panel(
            "[bold green]⬡ Connection Status:[/] [white]Active (NVIDIA NIM)[/]\n"
            "[bold yellow]⚙ Primary Reasoning:[/] [white]deepseek-ai/deepseek-r1[/]\n"
            "[bold blue]📐 Fallback Ladder:[/]  [white]deepseek-coder, qwen2.5-72b, llama-3.3-70b, phi-4[/]",
            border_style="cyan",
            padding=(0, 2)
        )
    )
    console.print("Type [bold yellow]/help[/] for a list of commands. Press [bold green]Alt+Enter[/] to submit multiline prompts.\n")

def print_help():
    help_text = "\n".join([f"[bold yellow]{cmd}[/] - {desc}" for cmd, desc in SLASH_COMMANDS.items()])
    console.print(Panel(help_text, title="Slash Command Manual", border_style="cyan", title_align="left"))

async def print_tasks():
    task_path = Path("/home/shaun/.gemini/antigravity-ide/brain/bb5fbcbe-90fd-4c47-aa08-f0105ba53197/task.md")
    if task_path.exists():
        console.print(Panel(task_path.read_text(), title="Jarvis Implementation Tasks", border_style="cyan"))
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
        @self.kb.add("escape", "enter")
        @self.kb.add("alt-enter")
        def _submit(event):
            event.current_buffer.validate_and_handle()

        @self.kb.add("enter")
        def _enter(event):
            event.current_buffer.insert_text("\n")

        @self.kb.add("/")
        def _slash_complete(event):
            event.current_buffer.insert_text("/")
            event.current_buffer.start_completion(select_first=False)

    def _bottom_toolbar(self):
        return HTML(
            f" <b>Session:</b> {self.session_id} | "
            f"<b>Primary:</b> deepseek-r1 | "
            f"<b>API Endpoint:</b> NIM (integrate.api.nvidia.com) | "
            f"Type / for commands"
        )

    async def init(self):
        await self.memory.init_db()
        if not self.api_key:
            console.print("[bold red]WARNING: NVIDIA_API_KEY environment variable is not set. API calls will fail.[/]")
        
        # Load local skills
        skills_tools = load_skills_from_dir(Path("/home/shaun/jarvis/skills"))
        
        # Register forge_skill tool
        all_tools = [forge_skill] + skills_tools
        
        # Inject user profile into system instructions
        profile = await self.memory.build_profile_prompt()
        custom_instructions = f"{DEFAULT_SYSTEM_PROMPT}\n\n{profile}"
        
        self.agent = create_jarvis_agent(
            api_key=self.api_key or "",
            instructions_override=custom_instructions,
            tools=all_tools
        )
        
        # Log session startup
        await self.memory.create_session(
            session_id=self.session_id,
            model="trinity-council",
            system_prompt=custom_instructions
        )

    async def handle_slash(self, cmd: str) -> bool:
        parts = cmd.split()
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
            console.print(f"[bold green]✓ Started new dialogue session: {self.session_id}[/]\n")
            return True
        elif base == "/tasks":
            await print_tasks()
            return True
        elif base == "/skills":
            skills_tools = load_skills_from_dir(Path("/home/shaun/jarvis/skills"))
            if not skills_tools:
                console.print("[yellow]No custom skills forged yet.[/]")
            else:
                lines = [f"- [bold green]{t.name}[/]: {t.description}" for t in skills_tools]
                console.print(Panel("\n".join(lines), title="Forged Skill Modules", border_style="cyan"))
            return True
        elif base == "/models":
            lines = [f"- {m}" for m in DEFAULT_FALLBACK_LADDER]
            console.print(Panel("\n".join(lines), title="Trinity Fallback Ladder", border_style="cyan"))
            return True
        elif base == "/exit":
            console.print("\n[dim]Goodbye. ⚙[/]\n")
            sys.exit(0)
        return False

    async def run_loop(self):
        print_splash()
        
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
                    HTML("<cyan bold>❯ </cyan>"),
                    placeholder=HTML("<style fg='#5c6370'>Ask anything, or type / for commands…</style>")
                )
                user_input = user_input.strip()
                if not user_input:
                    continue
                
                if user_input.startswith("/"):
                    handled = await self.handle_slash(user_input)
                    if not handled:
                        console.print(f"[red]Unknown slash command: {user_input}[/]")
                    continue
                
                # Execute agent turn
                await self.execute_turn(user_input)
                
            except KeyboardInterrupt:
                console.print("\n[bold red]⚡ Interrupted[/]\n")
                continue
            except EOFError:
                console.print("\n[dim]Goodbye. ⚙[/]\n")
                break
            except Exception as e:
                console.print(f"[bold red]System Error:[/] {e}")
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
        
        active_task = None
        
        async def run_agent():
            nonlocal live, raw_buffer, reasoning_text, response_text
            try:
                # We start streaming the response
                async for chunk in self.agent.run(messages=agent_msgs, stream=True):
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
                            renderables.append(Panel(reasoning_text, title="Thinking Processes", border_style="dim yellow", title_align="left"))
                        if response_text:
                            renderables.append(Markdown(response_text))
                            
                        live.update(Group(*renderables))
                        
                    if chunk.finish_reason:
                        if live:
                            live.stop()
                            live = None
                        raw_buffer = ""
                        # Store agent turn response
                        final_text = ""
                        if reasoning_text:
                            final_text += f"<think>\n{reasoning_text}\n</think>\n"
                        final_text += response_text
                        await self.memory.add_message(
                            session_id=self.session_id,
                            role="assistant",
                            content=final_text
                        )
                        console.print() # separating line
                        
            except asyncio.CancelledError:
                if live:
                    live.stop()
                console.print("\n[bold red]⚡ Interrupted[/]\n")
            except Exception as ex:
                if live:
                    live.stop()
                console.print(f"\n[bold red]Error during response generation:[/] {ex}")
                logger.exception("Error in execute_turn run_agent")
                
        # Start executing
        active_task = asyncio.create_task(run_agent())
        try:
            await active_task
        except KeyboardInterrupt:
            active_task.cancel()
            await active_task
            console.print("\n[bold red]⚡ Interrupted[/]\n")

async def main():
    tui = JarvisTUI()
    await tui.init()
    await tui.run_loop()

if __name__ == "__main__":
    asyncio.run(main())
