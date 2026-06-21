"""Parse and compile subagent soul markdown files (frontmatter + operational rules)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jarvis.config.paths import get_subagent_dir
from jarvis.core.simple_yaml import parse_simple_yaml


@dataclass
class SoulDoc:
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""


def _parse_frontmatter_lists(frontmatter_block: str, base: dict[str, Any]) -> dict[str, Any]:
    """Extend parse_simple_yaml with `- item` list lines for known keys."""
    list_keys = {"owns", "forbidden", "tools"}
    current_list_key: str | None = None
    for line in frontmatter_block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current_list_key:
            base.setdefault(current_list_key, [])
            if isinstance(base[current_list_key], list):
                base[current_list_key].append(stripped[2:].strip().strip('"').strip("'"))
            continue
        if ":" in stripped and not stripped.startswith("-"):
            key = stripped.split(":", 1)[0].strip()
            val = stripped.split(":", 1)[1].strip()
            if val == "" and key in list_keys:
                base[key] = []
                current_list_key = key
            else:
                current_list_key = None
    return base


def parse_soul_file(path: Path) -> SoulDoc:
    if not path.exists():
        return SoulDoc()
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return SoulDoc(body=content.strip())

    parts = content.split("---", 2)
    if len(parts) < 3:
        return SoulDoc(body=content.strip())

    fm_block = parts[1].strip()
    body = parts[2].strip()
    frontmatter = parse_simple_yaml(fm_block)
    frontmatter = _parse_frontmatter_lists(fm_block, frontmatter)
    return SoulDoc(frontmatter=frontmatter, body=body)


def compile_instructions(doc: SoulDoc, *, include_team_contract: bool = True) -> str:
    sections = [doc.body] if doc.body else []
    if not include_team_contract:
        return "\n\n".join(sections).strip()

    fm = doc.frontmatter
    contract_lines: list[str] = []
    reports_to = fm.get("reports_to")
    if reports_to:
        contract_lines.append(f"- Reports to: **{reports_to}**")
    owns = fm.get("owns")
    if isinstance(owns, list) and owns:
        contract_lines.append("- Owns:")
        contract_lines.extend(f"  - {item}" for item in owns)
    forbidden = fm.get("forbidden")
    if isinstance(forbidden, list) and forbidden:
        contract_lines.append("- Forbidden:")
        contract_lines.extend(f"  - {item}" for item in forbidden)
    if contract_lines:
        sections.append("# TEAM CONTRACT\n" + "\n".join(contract_lines))
    return "\n\n".join(sections).strip()


def load_compiled_soul(name: str) -> tuple[SoulDoc, str]:
    name = name.lower().strip()
    soul_path = get_subagent_dir(name) / f"{name}_soul.md"
    doc = parse_soul_file(soul_path)
    return doc, compile_instructions(doc)
