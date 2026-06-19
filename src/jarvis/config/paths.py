import os
from pathlib import Path


def get_workspace_root() -> Path:
    """Return the Jarvis workspace root, honoring JARVIS_WORKSPACE_ROOT when set."""
    env_root = os.environ.get("JARVIS_WORKSPACE_ROOT", "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    # src/jarvis/config/paths.py -> parents[3] == repo root
    return Path(__file__).resolve().parents[3]


def get_data_dir() -> Path:
    return Path(os.environ.get("JARVIS_DATA_DIR", get_workspace_root() / "data"))


def get_db_path() -> Path:
    return Path(os.environ.get("JARVIS_DB_PATH", get_data_dir() / "jarvis.db"))


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
