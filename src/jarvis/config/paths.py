import os
from pathlib import Path
from typing import Optional


def _env_path(name: str) -> Optional[Path]:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    return Path(value).expanduser()


def get_workspace_root() -> Path:
    """Return the Jarvis workspace root, honoring JARVIS_WORKSPACE_ROOT when set."""
    env_root = _env_path("JARVIS_WORKSPACE_ROOT")
    if env_root:
        return env_root.resolve()
    # src/jarvis/config/paths.py -> parents[3] == repo root
    return Path(__file__).resolve().parents[3]


def get_data_dir() -> Path:
    override = _env_path("JARVIS_DATA_DIR")
    if override:
        return override.resolve()
    return (get_workspace_root() / "data").resolve()


def get_db_path() -> Path:
    override = _env_path("JARVIS_DB_PATH")
    if override:
        return override.resolve()
    return get_data_dir() / "jarvis.db"


def get_skills_dir() -> Path:
    return get_workspace_root() / "skills"


def get_subagent_dir(name: str) -> Path:
    return get_skills_dir() / name.lower().strip()


def get_webvision_dir() -> Path:
    return get_workspace_root() / "webvision"


def get_web_dist_dir() -> Path:
    return get_workspace_root() / "web" / "dist"


def get_env_file() -> Path:
    return get_workspace_root() / ".env"


def get_venv_python() -> Path:
    return get_workspace_root() / ".venv" / "bin" / "python3"


def resolve_workspace_path(path: str | Path) -> Path:
    """Resolve a path relative to the workspace root when not absolute."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return get_workspace_root() / candidate
