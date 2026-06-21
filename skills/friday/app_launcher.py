"""Linux desktop application discovery and launch via Freedesktop .desktop entries."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agent_framework import tool

logger = logging.getLogger("jarvis.skills.app_launcher")

_FIELD_CODE_RE = re.compile(r"%[fFuUdDnNickvm]")


@dataclass(frozen=True)
class DesktopApp:
    desktop_id: str
    name: str
    generic_name: str
    comment: str
    exec_line: str
    path: str
    categories: str
    working_dir: str

    def match_score(self, query: str) -> int:
        if not query:
            return 1
        q = query.lower().strip()
        if not q:
            return 1
        score = 0
        blob = " ".join(
            [self.desktop_id, self.name, self.generic_name, self.comment, self.categories]
        ).lower()
        if q in blob:
            score += 10
        tokens = [t for t in re.split(r"[\s\-_]+", q) if t]
        for token in tokens:
            if token in blob:
                score += 5
            if self.name.lower() == token or self.desktop_id.lower().startswith(token):
                score += 15
        if self.desktop_id.lower().replace(".desktop", "") == q.replace(".desktop", ""):
            score += 50
        return score


def _desktop_search_dirs() -> list[Path]:
    dirs: list[Path] = []
    xdg = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
    for base in xdg.split(":"):
        candidate = Path(base) / "applications"
        if candidate.is_dir():
            dirs.append(candidate)
    local = Path.home() / ".local" / "share" / "applications"
    if local.is_dir():
        dirs.append(local)
    for extra in (
        Path("/var/lib/flatpak/exports/share/applications"),
        Path.home() / ".local/share/flatpak/exports/share/applications",
        Path("/snap/applications"),
    ):
        if extra.is_dir():
            dirs.append(extra)
    seen: set[Path] = set()
    unique: list[Path] = []
    for d in dirs:
        resolved = d.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def _parse_desktop_file(path: Path) -> Optional[dict[str, str]]:
    data: dict[str, str] = {}
    in_entry = False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "[Desktop Entry]":
            in_entry = True
            continue
        if line.startswith("[") and line != "[Desktop Entry]":
            break
        if not in_entry or "=" not in line:
            continue
        key, val = line.split("=", 1)
        data[key.strip()] = val.strip()
    if not data:
        return None
    return data


def _iter_desktop_apps() -> list[DesktopApp]:
    apps: list[DesktopApp] = []
    seen_ids: set[str] = set()
    for directory in _desktop_search_dirs():
        for path in sorted(directory.glob("*.desktop")):
            desktop_id = path.name
            if desktop_id in seen_ids:
                continue
            meta = _parse_desktop_file(path)
            if not meta:
                continue
            if meta.get("Type", "Application") != "Application":
                continue
            if meta.get("NoDisplay", "").lower() == "true":
                continue
            if meta.get("Hidden", "").lower() == "true":
                continue
            exec_line = meta.get("Exec", "").strip()
            if not exec_line:
                continue
            seen_ids.add(desktop_id)
            apps.append(
                DesktopApp(
                    desktop_id=desktop_id,
                    name=meta.get("Name", desktop_id),
                    generic_name=meta.get("GenericName", ""),
                    comment=meta.get("Comment", ""),
                    exec_line=exec_line,
                    path=str(path),
                    categories=meta.get("Categories", ""),
                    working_dir=meta.get("Path", ""),
                )
            )
    return apps


def _rank_apps(query: str, limit: int) -> list[DesktopApp]:
    limit = min(max(int(limit), 1), 50)
    scored = [(app.match_score(query), app) for app in _iter_desktop_apps()]
    scored = [(s, a) for s, a in scored if s > 0 or not query.strip()]
    scored.sort(key=lambda pair: (-pair[0], pair[1].name.lower()))
    return [app for _, app in scored[:limit]]


def _clean_exec(exec_line: str) -> list[str]:
    cleaned = _FIELD_CODE_RE.sub("", exec_line).strip()
    # Basic split — sufficient for typical .desktop Exec lines
    return cleaned.split()


def _launch_env() -> dict[str, str]:
    env = os.environ.copy()
    if not env.get("DISPLAY") and Path("/tmp/.X11-unix").exists():
        # Common default when server subprocess inherits no display
        for display in (":0", ":1"):
            if (Path("/tmp/.X11-unix") / display.lstrip(":")).exists():
                env.setdefault("DISPLAY", display)
                break
    return env


def _try_gtk_launch(desktop_id: str, env: dict[str, str]) -> tuple[bool, str]:
    stem = desktop_id[:-8] if desktop_id.endswith(".desktop") else desktop_id
    if shutil.which("gtk-launch"):
        res = subprocess.run(
            ["gtk-launch", stem],
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )
        rc = res.returncode
        if rc == 0:
            return True, f"gtk-launch {stem}"
        err = str(res.stderr or res.stdout or "gtk-launch failed").strip()
        return False, err or "gtk-launch failed"
    return False, "gtk-launch not found"


def _try_gio_launch(desktop_path: str, env: dict[str, str]) -> tuple[bool, str]:
    if shutil.which("gio"):
        res = subprocess.run(
            ["gio", "launch", desktop_path],
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )
        if res.returncode == 0:
            return True, f"gio launch {desktop_path}"
        err = str(res.stderr or res.stdout or "gio launch failed").strip()
        return False, err or "gio launch failed"
    return False, "gio not found"


def _try_exec_line(app: DesktopApp, env: dict[str, str]) -> tuple[bool, str]:
    argv = _clean_exec(app.exec_line)
    if not argv:
        return False, "empty Exec line"
    try:
        cwd = app.working_dir or None
        subprocess.Popen(
            argv,
            env=env,
            cwd=cwd,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True, " ".join(argv)
    except Exception as exc:
        return False, str(exc)


def _launch_app(app: DesktopApp) -> dict:
    env = _launch_env()
    errors: list[str] = []
    for attempt in (
        lambda: _try_gtk_launch(app.desktop_id, env),
        lambda: _try_gio_launch(app.path, env),
        lambda: _try_exec_line(app, env),
    ):
        ok, detail = attempt()
        if ok:
            return {
                "success": True,
                "desktop_id": app.desktop_id,
                "name": app.name,
                "method": detail,
                "path": app.path,
            }
        errors.append(detail)
    return {
        "success": False,
        "error": "; ".join(errors),
        "desktop_id": app.desktop_id,
        "name": app.name,
    }


@tool(approval_mode="never_require")
def stark_os_armor_list_apps(query: str = "", limit: int = 25) -> str:
    """
    Search installed Linux applications from Freedesktop .desktop entries.
    Args:
        query: Substring to match against app name, generic name, comment, or desktop id (empty = list all).
        limit: Maximum results (default 25, max 50).
    Returns:
        JSON list of matching applications with desktop_id and path.
    """
    try:
        matches = _rank_apps(query, limit)
        return json.dumps(
            {
                "success": True,
                "query": query,
                "count": len(matches),
                "apps": [
                    {
                        "desktop_id": a.desktop_id,
                        "name": a.name,
                        "generic_name": a.generic_name,
                        "comment": a.comment,
                        "path": a.path,
                        "categories": a.categories,
                    }
                    for a in matches
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.exception("list_apps failed")
        return json.dumps({"success": False, "error": str(exc)})


@tool(approval_mode="always_require")
def stark_os_armor_launch_app(app_name: str) -> str:
    """
    Launch a Linux GUI application by name or desktop id (e.g. 'notes', 'firefox', 'org.gnome.TextEditor').
    Resolves Freedesktop .desktop entries and launches via gtk-launch, gio, or Exec fallback.
    Args:
        app_name: Human name, keyword, or desktop id to match.
    Returns:
        JSON report with launch method or error (includes candidate list if ambiguous).
    """
    query = app_name.strip()
    if not query:
        return json.dumps({"success": False, "error": "app_name is required."})

    try:
        ranked = _rank_apps(query, limit=10)
        if not ranked:
            return json.dumps(
                {
                    "success": False,
                    "error": f"No application matched '{query}'.",
                    "hint": "Call stark_os_armor_list_apps with a keyword to discover installed apps.",
                }
            )

        best = ranked[0]
        if len(ranked) > 1:
            second_score = ranked[1].match_score(query)
            best_score = best.match_score(query)
            if best_score > 0 and second_score > 0 and best_score == second_score:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Ambiguous match for '{query}'.",
                        "candidates": [
                            {"desktop_id": a.desktop_id, "name": a.name, "path": a.path}
                            for a in ranked[:5]
                        ],
                    },
                    indent=2,
                )

        result = _launch_app(best)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.exception("launch_app failed")
        return json.dumps({"success": False, "error": str(exc)})
