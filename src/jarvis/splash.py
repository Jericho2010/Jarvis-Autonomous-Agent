from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.align import Align
from rich.table import Table
from prompt_toolkit.styles import Style
from jarvis.completers import SLASH_COMMANDS

console = Console()

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
    # Note: Task path from active environment
    task_path = Path("/home/shaun/.gemini/antigravity-cli/brain/5ae93a25-73b8-4be0-ad5a-0a0d63cb8e35/task.md")
    if task_path.exists():
        console.print(Panel(task_path.read_text(), title="Jarvis Implementation Tasks", border_style="#FFD700"))
    else:
        console.print("[yellow]No tasks file found at active path.[/]")

def render_splash(port: int, session_id: str, session_title: str = None):
    reactor_graphic = (
        "      [#00F0FF]  .---.  [/]\n"
        "      [#00F0FF] /  [bold #00E5FF]⬡[/]  \\ [/]\n"
        "      [#00F0FF]| [bold #00E5FF]⬡[/] [bold #FFD700]⬢[/] [bold #00E5FF]⬡[/] |[/]\n"
        "      [#00F0FF] \\  [bold #00E5FF]⬡[/]  / [/]\n"
        "      [#00F0FF]  '---'  [/]"
    )

    info_table = Table.grid(padding=(0, 2))
    info_table.add_column()
    info_table.add_column(style="bold #E63946")
    info_table.add_column()
    info_table.add_row("[#00F0FF]⬡[/]", "STATUS:", "[bold green]ONLINE (API SERVER)[/]")
    info_table.add_row("[#00F0FF]⬡[/]", "HOST CORE:", "[bold #FFD700]NVIDIA NIM APIs[/]")
    info_table.add_row("[#00F0FF]⬡[/]", "ROUTING:", "[bold #FFD700]Stark Core Matrix[/]")
    info_table.add_row("[#00F0FF]⬡[/]", "ENDPOINT:", f"[white]http://localhost:{port}[/]")
    info_table.add_row("[#00F0FF]⬡[/]", "SESSION:", f"[white]{session_title or session_id}[/]")
    
    splash_table = Table.grid(padding=(0, 4))
    splash_table.add_row(reactor_graphic, info_table)

    console.print(ASCII_ART)
    console.print(Panel(
        Align.center(splash_table),
        title="[bold #FFD700]MARK XLVIII - DECOUPLED COGNITIVE INTERFACE[/]",
        border_style="#E63946",
        padding=(1, 2)
    ))
