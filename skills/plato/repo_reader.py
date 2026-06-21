"""Read-only workspace file tools for Plato code review."""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

from agent_framework import tool

from jarvis.config.paths import get_workspace_root, resolve_workspace_path

_SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "webvision"}
_TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".yaml", ".yml", ".json", ".toml", ".ini",
    ".ts", ".tsx", ".js", ".jsx", ".html", ".css", ".sh", ".sql",
}


def _within_workspace(path: Path) -> bool:
    root = get_workspace_root().resolve()
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def _safe_path(file_path: str) -> Path | None:
    try:
        path = resolve_workspace_path(file_path).resolve()
    except Exception:
        return None
    if not _within_workspace(path):
        return None
    return path


@tool(approval_mode="never_require")
def read_repo_file(file_path: str, start_line: int = 1, max_lines: int = 400) -> str:
    """
    Read a UTF-8 text file from the workspace (read-only).
    Args:
        file_path: Path relative to workspace root or absolute within workspace.
        start_line: 1-based line to start reading from.
        max_lines: Maximum lines to return (capped at 400).
    Returns:
        JSON with content or error.
    """
    path = _safe_path(file_path)
    if path is None:
        return json.dumps({"success": False, "error": "Path outside workspace or invalid."})
    if not path.is_file():
        return json.dumps({"success": False, "error": f"File not found: {file_path}"})

    start_line = max(1, int(start_line))
    max_lines = min(max(1, int(max_lines)), 400)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return json.dumps({"success": False, "error": "File is not UTF-8 text."})

    total = len(lines)
    slice_start = start_line - 1
    slice_end = slice_start + max_lines
    chunk = lines[slice_start:slice_end]
    truncated = slice_end < total
    numbered = [f"{i + start_line:5d}| {line}" for i, line in enumerate(chunk)]
    return json.dumps({
        "success": True,
        "path": str(path.relative_to(get_workspace_root())),
        "start_line": start_line,
        "end_line": start_line + len(chunk) - 1 if chunk else start_line,
        "total_lines": total,
        "truncated": truncated,
        "content": "\n".join(numbered),
    }, indent=2)


@tool(approval_mode="never_require")
def list_repo_files(relative_dir: str = ".", glob_pattern: str = "**/*") -> str:
    """
    List files under a workspace directory (bounded, read-only).
    Args:
        relative_dir: Directory relative to workspace root.
        glob_pattern: Glob pattern (default all files recursively).
    Returns:
        JSON array of relative paths (max 200).
    """
    base = _safe_path(relative_dir)
    if base is None:
        return json.dumps({"success": False, "error": "Path outside workspace or invalid."})
    if not base.is_dir():
        return json.dumps({"success": False, "error": f"Not a directory: {relative_dir}"})

    root = get_workspace_root().resolve()
    cap = 200
    results: list[str] = []
    truncated = False

    for path in base.rglob("*"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        rel = str(path.relative_to(root))
        if not fnmatch.fnmatch(rel, glob_pattern.lstrip("./")):
            if glob_pattern != "**/*" and not fnmatch.fnmatch(path.name, glob_pattern):
                continue
        results.append(rel)
        if len(results) >= cap:
            truncated = True
            break

    results.sort()
    return json.dumps({
        "success": True,
        "count": len(results),
        "truncated": truncated,
        "files": results,
    }, indent=2)


@tool(approval_mode="never_require")
def grep_repo_files(pattern: str, relative_dir: str = ".", max_matches: int = 50) -> str:
    """
    Search workspace text files for a regex pattern (read-only).
    Args:
        pattern: Regular expression to search for.
        relative_dir: Directory relative to workspace root.
        max_matches: Maximum matches to return (capped at 50).
    Returns:
        JSON list of {path, line, text} matches.
    """
    base = _safe_path(relative_dir)
    if base is None:
        return json.dumps({"success": False, "error": "Path outside workspace or invalid."})
    if not base.is_dir():
        return json.dumps({"success": False, "error": f"Not a directory: {relative_dir}"})

    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return json.dumps({"success": False, "error": f"Invalid regex: {exc}"})

    root = get_workspace_root().resolve()
    max_matches = min(max(1, int(max_matches)), 50)
    matches: list[dict[str, str | int]] = []
    truncated = False

    for path in base.rglob("*"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in _TEXT_SUFFIXES and path.name not in ("Dockerfile", "Makefile"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = str(path.relative_to(root))
        for line_no, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append({"path": rel, "line": line_no, "text": line.strip()[:200]})
                if len(matches) >= max_matches:
                    truncated = True
                    break
        if truncated:
            break

    return json.dumps({
        "success": True,
        "pattern": pattern,
        "count": len(matches),
        "truncated": truncated,
        "matches": matches,
    }, indent=2)
