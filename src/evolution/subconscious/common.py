import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from jarvis.config.paths import get_data_dir, get_env_file, get_workspace_root

LOG = logging.getLogger("jarvis.evolution")


def bootstrap() -> None:
    """Load env and ensure src is on sys.path for cron invocations."""
    load_dotenv(get_env_file())
    src = str(get_workspace_root() / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def setup_logging() -> None:
    log_file = get_data_dir() / "subconscious.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            filename=str(log_file),
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )


def require_api_key() -> str:
    api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not api_key:
        LOG.error("Subconscious // NVIDIA_API_KEY missing.")
        raise RuntimeError("NVIDIA_API_KEY is not set.")
    return api_key
