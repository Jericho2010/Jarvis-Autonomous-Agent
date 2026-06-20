import os
import logging
import subprocess
from pathlib import Path
from datetime import datetime

from jarvis.config.paths import get_workspace_root

logger = logging.getLogger("jarvis.sync")

EVOLUTION_SYNC_PATHS = (
    "skills",
    "skills_staging",
    "data/evolution_logs",
    "data/evolution_manifest.json",
)


def get_current_repo_name() -> str:
    try:
        # Try to parse repo name from git remote
        res = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=str(get_workspace_root())
        )
        if res.returncode == 0 and res.stdout.strip():
            url = res.stdout.strip()
            # extract repo name (e.g. from https://github.com/owner/repo.git or git@github.com:owner/repo.git)
            parts = url.rstrip("/").replace(".git", "").split("/")
            if parts:
                return parts[-1]
    except Exception:
        pass
    return "jarvis"


def sync_evolution_artifacts(commit_msg: str) -> bool:
    """
    Stage, commit, and push only skills and evolution artifacts.
    Uses GITHUB_PERSONAL_ACCESS_TOKEN when configured.
    """
    token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not token or token == "your_pat_here":
        logger.warning("GitHub Sync // GITHUB_PERSONAL_ACCESS_TOKEN not configured. Skipping remote push.")
        print("⚠️ GITHUB_PERSONAL_ACCESS_TOKEN not set. Local commit only.")
        token = None

    repo_root = get_workspace_root()
    if not repo_root.exists():
        logger.error("GitHub Sync // Repo root %s does not exist.", repo_root)
        return False

    try:
        if not (repo_root / ".git").exists():
            logger.info("GitHub Sync // Initializing git repository...")
            subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_root), check=True)

        for rel in EVOLUTION_SYNC_PATHS:
            target = repo_root / rel
            if target.exists():
                subprocess.run(["git", "add", rel], cwd=str(repo_root), check=True)

        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            check=True,
        )

        if not status_res.stdout.strip():
            logger.info("GitHub Sync // No evolution artifact changes detected.")
            print("✓ Evolution artifacts unchanged. No commit required.")
            return True

        subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(repo_root), check=True)
        print(f"✓ Committed changes: '{commit_msg}'")

        if not token:
            return True

        repo_name = get_current_repo_name()
        origin_url = f"https://github.com/Jericho2010/{repo_name}.git"
        authed_url = f"https://{token}@github.com/Jericho2010/{repo_name}.git"

        remote_check = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )

        if remote_check.returncode == 0:
            subprocess.run(["git", "remote", "set-url", "origin", authed_url], cwd=str(repo_root), check=True)
        else:
            subprocess.run(["git", "remote", "add", "origin", authed_url], cwd=str(repo_root), check=True)

        print("📤 Pushing evolution artifacts to remote main branch...")
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=str(repo_root), check=True)
        print("✓ Successfully pushed to remote GitHub repository.")

        subprocess.run(["git", "remote", "set-url", "origin", origin_url], cwd=str(repo_root), check=True)
        logger.info("GitHub Sync // Evolution sync complete, remote URL cleaned.")
        return True

    except Exception as e:
        logger.exception("GitHub Sync // Evolution sync failed")
        print(f"❌ GitHub sync failed: {e}")
        try:
            repo_name = get_current_repo_name()
            subprocess.run(
                ["git", "remote", "set-url", "origin", f"https://github.com/Jericho2010/{repo_name}.git"],
                cwd=str(repo_root),
            )
        except Exception:
            pass
        return False


def sync_workspace(saint_name: str = "Unknown") -> bool:
    """Backward-compatible wrapper — commits evolution artifacts only."""
    commit_msg = f"evolution: subconscious — {saint_name} ({datetime.now().strftime('%Y-%m-%d')})"
    return sync_evolution_artifacts(commit_msg)
