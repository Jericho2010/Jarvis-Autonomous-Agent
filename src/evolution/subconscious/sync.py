import logging

from jarvis.sync.github_sync import sync_evolution_artifacts

LOG = logging.getLogger("jarvis.evolution.sync")


def sync_after_evolution(commit_msg: str) -> bool:
    """Commit and push skills + evolution artifacts only."""
    try:
        return sync_evolution_artifacts(commit_msg)
    except Exception:
        LOG.exception("Evolution git sync failed")
        return False
