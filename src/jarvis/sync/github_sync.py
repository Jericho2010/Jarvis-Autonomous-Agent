import os
import logging
import subprocess
from pathlib import Path
from datetime import datetime

from jarvis.config.paths import get_workspace_root

logger = logging.getLogger("jarvis.sync")

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

def sync_workspace(saint_name: str) -> bool:
    """
    Stages, commits, and pushes reflection summaries and custom skills to GitHub.
    Uses the GITHUB_PERSONAL_ACCESS_TOKEN for authentication and masks it afterwards.
    """
    token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not token or token == "your_pat_here":
        logger.warning("GitHub Sync // GITHUB_PERSONAL_ACCESS_TOKEN not configured. Skipping remote push.")
        print("⚠️ GITHUB_PERSONAL_ACCESS_TOKEN not set. Local commit only.")
        token = None

    repo_root = get_workspace_root()
    if not repo_root.exists():
        logger.error(f"GitHub Sync // Repo root {repo_root} does not exist.")
        return False

    try:
        # 1. Check if git repository is initialized
        if not (repo_root / ".git").exists():
            logger.info("GitHub Sync // Initializing git repository...")
            subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_root), check=True)

        # 2. Stage changes
        subprocess.run(["git", "add", "."], cwd=str(repo_root), check=True)

        # 3. Check for modifications
        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            check=True
        )
        
        if not status_res.stdout.strip():
            logger.info("GitHub Sync // No changes detected. Workspace is clean.")
            print("✓ Workspace is clean. No push required.")
            return True

        # 4. Commit changes
        commit_msg = f"evolution: subconscious alignment - Saint {saint_name} ({datetime.now().strftime('%Y-%m-%d')})"
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(repo_root), check=True)
        print(f"✓ Committed changes: '{commit_msg}'")

        if not token:
            return True

        # 5. Push using PAT (temporary URL replacement)
        repo_name = get_current_repo_name()
        origin_url = f"https://github.com/Jericho2010/{repo_name}.git"
        authed_url = f"https://{token}@github.com/Jericho2010/{repo_name}.git"

        # Check if origin remote is set
        remote_check = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=str(repo_root)
        )
        
        if remote_check.returncode == 0:
            subprocess.run(["git", "remote", "set-url", "origin", authed_url], cwd=str(repo_root), check=True)
        else:
            subprocess.run(["git", "remote", "add", "origin", authed_url], cwd=str(repo_root), check=True)

        # Push to remote main
        print("📤 Pushing to remote main branch...")
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=str(repo_root), check=True)
        print("✓ Successfully pushed to remote GitHub repository.")

        # 6. Restore public unauthenticated URL to prevent credentials leakage in .git/config
        subprocess.run(["git", "remote", "set-url", "origin", origin_url], cwd=str(repo_root), check=True)
        logger.info("GitHub Sync // Sync complete, remote URL cleaned.")
        return True

    except Exception as e:
        logger.exception("GitHub Sync // Sync failed")
        print(f"❌ GitHub sync failed: {e}")
        # Safeguard: try to clean up remote url anyway
        try:
            repo_name = get_current_repo_name()
            subprocess.run(
                ["git", "remote", "set-url", "origin", f"https://github.com/Jericho2010/{repo_name}.git"],
                cwd=str(repo_root)
            )
        except Exception:
            pass
        return False
