import json
import logging
import shutil
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from jarvis.config.paths import (
    get_evolution_manifest_path,
    get_skills_dir,
    get_staging_dir,
)

LOG = logging.getLogger("jarvis.evolution.staging")

Source = Literal["pray", "dream"]
Status = Literal["pending", "approved", "rejected"]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_skill_name(name: str) -> str:
    cleaned = "".join(c for c in name.strip().lower() if c.isalnum() or c in "_-")
    return cleaned.replace("-", "_")


def ensure_staging_dirs() -> None:
    root = get_staging_dir()
    for sub in ("pray", "dream", "rejected"):
        (root / sub).mkdir(parents=True, exist_ok=True)


def load_manifest() -> Dict[str, Any]:
    path = get_evolution_manifest_path()
    if not path.exists():
        return {"skills": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        LOG.warning("Corrupt evolution manifest; resetting skills map.")
        return {"skills": {}}


def save_manifest(manifest: Dict[str, Any]) -> None:
    path = get_evolution_manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _staging_file(source: Source, name: str) -> Path:
    return get_staging_dir() / source / f"{name}.py"


def _rejected_file(name: str) -> Path:
    return get_staging_dir() / "rejected" / f"{name}.py"


def _name_taken(name: str) -> bool:
    if (get_skills_dir() / f"{name}.py").exists():
        return True
    manifest = load_manifest()
    entry = manifest.get("skills", {}).get(name)
    if entry and entry.get("status") == "pending":
        return True
    if _rejected_file(name).exists():
        return True
    for source in ("pray", "dream"):
        if _staging_file(source, name).exists():
            return True
    return False


def resolve_unique_name(proposed: str) -> Tuple[str, Optional[str]]:
    """Return (final_name, original_name if renamed)."""
    base = normalize_skill_name(proposed)
    if not base:
        base = f"auto_skill_{datetime.now().strftime('%m%d')}"

    if not _name_taken(base):
        return base, None

    original = base
    counter = 0
    while True:
        counter += 1
        suffix = datetime.now().strftime("%Y%m%d")
        if counter > 1:
            suffix = f"{suffix}_{counter}"
        candidate = f"{base}_{suffix}"
        if not _name_taken(candidate):
            return candidate, original


def is_dream_duplicate_of_pray(proposed_name: str, summary: str) -> bool:
    """Same-night Dream dedup against Pray staging."""
    today = datetime.now().strftime("%Y-%m-%d")
    manifest = load_manifest()
    norm_proposed = normalize_skill_name(proposed_name)

    for name, entry in manifest.get("skills", {}).items():
        if entry.get("status") != "pending" or entry.get("source") != "pray":
            continue
        forged = entry.get("forged_at", "")
        if not forged.startswith(today):
            continue
        if normalize_skill_name(name) == norm_proposed:
            return True
        pray_summary = entry.get("summary", "")
        if pray_summary and summary:
            if SequenceMatcher(None, pray_summary.lower(), summary.lower()).ratio() >= 0.75:
                return True

    pray_dir = get_staging_dir() / "pray"
    if pray_dir.exists():
        for f in pray_dir.glob("*.py"):
            if normalize_skill_name(f.stem) == norm_proposed:
                return True
    return False


def register_staged_skill(
    *,
    name: str,
    source: Source,
    summary: str,
    test_command: str,
    test_passed: bool,
    evolution_log: str,
    original_name: Optional[str] = None,
) -> None:
    manifest = load_manifest()
    skills = manifest.setdefault("skills", {})
    previous_entries: List[Dict[str, Any]] = []
    if name in skills:
        old = skills[name]
        previous_entries = list(old.get("previous_entries", []))
        if old.get("status") == "rejected":
            prev = dict(old)
            prev.pop("previous_entries", None)
            previous_entries.append(prev)

    entry: Dict[str, Any] = {
        "status": "pending",
        "source": source,
        "summary": summary,
        "original_name": original_name,
        "forged_at": _now_iso(),
        "approved_at": None,
        "rejected_at": None,
        "test_command": test_command,
        "test_passed": test_passed,
        "evolution_log": evolution_log,
    }
    if previous_entries:
        entry["previous_entries"] = previous_entries
    skills[name] = entry
    save_manifest(manifest)


def find_pending_path(name: str) -> Optional[Tuple[Source, Path]]:
    norm = normalize_skill_name(name)
    for source in ("pray", "dream"):
        for f in (get_staging_dir() / source).glob("*.py"):
            if normalize_skill_name(f.stem) == norm:
                return source, f
    return None


def list_pending() -> List[Dict[str, Any]]:
    manifest = load_manifest()
    pending = []
    for name, entry in manifest.get("skills", {}).items():
        if entry.get("status") == "pending":
            pending.append({"name": name, **entry})
    pending.sort(key=lambda e: e.get("forged_at", ""), reverse=True)
    return pending


def list_rejected() -> List[Dict[str, Any]]:
    manifest = load_manifest()
    rejected = []
    for name, entry in manifest.get("skills", {}).items():
        if entry.get("status") == "rejected":
            rejected.append({"name": name, **entry})
    rejected.sort(key=lambda e: e.get("rejected_at", ""), reverse=True)
    return rejected


def get_skill_detail(name: str) -> Optional[Dict[str, Any]]:
    norm = normalize_skill_name(name)
    manifest = load_manifest()
    for skill_name, entry in manifest.get("skills", {}).items():
        if normalize_skill_name(skill_name) == norm:
            detail = {"name": skill_name, **entry}
            for sub in ("pray", "dream", "rejected"):
                p = get_staging_dir() / sub / f"{skill_name}.py"
                if p.exists():
                    detail["path"] = str(p)
                    detail["location"] = sub
                    break
            return detail
    return None


def _read_code_preview(path: Optional[str], lines: int = 30) -> str:
    if not path:
        return "(no file on disk)"
    p = Path(path)
    if not p.exists():
        return "(file missing)"
    text = p.read_text(encoding="utf-8")
    preview_lines = text.splitlines()[:lines]
    suffix = "\n..." if len(text.splitlines()) > lines else ""
    return "\n".join(preview_lines) + suffix


def format_skill_show(name: str) -> str:
    detail = get_skill_detail(name)
    if not detail:
        return f"No skill '{name}' in evolution manifest."

    lines = [
        f"Skill: {detail['name']}",
        f"Status: {detail.get('status')}",
        f"Source: {detail.get('source')}",
        f"Summary: {detail.get('summary', '')}",
        f"Forged: {detail.get('forged_at')}",
        f"Test: {'pass' if detail.get('test_passed') else 'fail'} — {detail.get('test_command', '')}",
        f"Log: {detail.get('evolution_log', '')}",
        f"Path: {detail.get('path', 'n/a')}",
        "",
        "--- code preview ---",
        _read_code_preview(detail.get("path")),
    ]
    if detail.get("original_name"):
        lines.insert(4, f"Original name: {detail['original_name']}")
    return "\n".join(lines)


def approve_skill(name: str) -> Tuple[bool, str]:
    ensure_staging_dirs()
    norm = normalize_skill_name(name)
    manifest = load_manifest()
    skill_key = None
    entry = None
    for k, v in manifest.get("skills", {}).items():
        if normalize_skill_name(k) == norm:
            skill_key = k
            entry = v
            break

    if not skill_key or entry.get("status") != "pending":
        return False, f"No pending staged skill named '{name}'."

    live_path = get_skills_dir() / f"{skill_key}.py"
    if live_path.exists():
        return False, f"Live skill '{skill_key}.py' already exists. Rename in staging before approving."

    located = find_pending_path(skill_key)
    if not located:
        return False, f"Pending skill '{skill_key}' not found in staging directories."

    _, staging_path = located
    get_skills_dir().mkdir(parents=True, exist_ok=True)
    shutil.copy2(staging_path, live_path)
    staging_path.unlink(missing_ok=True)

    entry["status"] = "approved"
    entry["approved_at"] = _now_iso()
    save_manifest(manifest)
    return True, f"Approved '{skill_key}' → skills/{skill_key}.py"


def approve_all() -> Tuple[int, List[str]]:
    pending = list_pending()
    if not pending:
        return 0, ["No pending skills to approve."]
    messages = []
    count = 0
    for item in pending:
        ok, msg = approve_skill(item["name"])
        messages.append(msg)
        if ok:
            count += 1
    return count, messages


def reject_skill(name: str) -> Tuple[bool, str]:
    ensure_staging_dirs()
    norm = normalize_skill_name(name)
    manifest = load_manifest()
    skill_key = None
    entry = None
    for k, v in manifest.get("skills", {}).items():
        if normalize_skill_name(k) == norm:
            skill_key = k
            entry = v
            break

    if not skill_key or entry.get("status") != "pending":
        return False, f"No pending staged skill named '{name}'."

    located = find_pending_path(skill_key)
    if not located:
        return False, f"Pending skill '{skill_key}' not found in staging directories."

    _, staging_path = located
    dest = _rejected_file(skill_key)
    if dest.exists():
        prev = dict(entry)
        entry.setdefault("previous_entries", []).append(prev)

    shutil.move(str(staging_path), str(dest))
    entry["status"] = "rejected"
    entry["rejected_at"] = _now_iso()
    save_manifest(manifest)
    return True, f"Rejected '{skill_key}' → skills_staging/rejected/{skill_key}.py"
