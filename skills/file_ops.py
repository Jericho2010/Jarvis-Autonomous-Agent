import os
from pathlib import Path
from agent_framework import tool
from jarvis.config.paths import resolve_workspace_path

@tool(approval_mode="never_require")
def read_file_content(file_path: str) -> str:
    """Reads the complete content of a file. Use absolute paths or paths relative to the workspace root."""
    try:
        path = resolve_workspace_path(file_path)
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Failed to read file: {e}"

@tool(approval_mode="never_require")
def write_file_content(file_path: str, content: str) -> str:
    """Writes content to a file, overwriting existing content. Will create parent directories."""
    try:
        path = resolve_workspace_path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Failed to write file: {e}"
