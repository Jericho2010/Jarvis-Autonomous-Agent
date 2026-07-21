import os
from pathlib import Path
from prompt_toolkit.completion import Completer, Completion

SLASH_COMMANDS = {
    "/help": "Show this help manual",
    "/new": "Start a fresh dialogue session",
    "/voicemode": "Toggle spoken butler voice: /voicemode [on|off]",
    "/switch": "Switch to an existing session: /switch [session_id|index]",
    "/agent": "Switch active session agent: /agent <homer|friday|plato|jarvis>",
    "/tasks": "Show the Jarvis implementation task list",
    "/skills": "List all loaded skill modules",
    "/evolve": "Review staged skills: /evolve [approve|reject|archive|show]",
    "/models": "List available cognitive models",
    "/model": "Set primary model: /model <name|index>",
    "/subagents": "List cognitive sub-agent profiles",
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
