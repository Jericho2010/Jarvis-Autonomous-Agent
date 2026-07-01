---
name: jarvis-harness
description: >-
  Expert harness engineering for the Jarvis repo: MAF agent loop, Stark NIM
  failover, handoffs, skills/subagents, memory, server/TUI, validation, and
  subconscious evolution. Use when working on Jarvis, digital hands, Homer,
  Friday, Plato, skill_forge, handoff_workflow, validate_handoffs, or extending
  the agent harness.
---

# Jarvis Harness Engineer

Personal MAF-based agent for Shaun. Repo: `/home/shaun/jarvis`. Linux Mint PC is the primary host (TUI + Web HUD on `:8008`).

Read this skill at the start of a new chat. Follow the user's latest message for the specific task — do not assume a roadmap unless they point to one.

## Resume and rumble (new chat)

1. **User intent first** — what are we doing this session? (fix, feature, validate, phone, refactor)
2. **Quick orientation** — `git status`, `git log -3 --oneline` if code changed recently
3. **Read targeted files** — use repo map below; don't load the whole tree
4. **ARCHITECTURE.md** — for deep cuts only ([reference.md](reference.md) for day-to-day)
5. **Validate** — run focused `pytest` on touched modules; use `scratch/validate_handoffs.py` for live handoff work on PC
6. **Task-specific plans** — if the user mentions a plan file, Cursor plan, or `scratch/plans/`, read that; otherwise improvise from code

## Repo map

| Path | Role |
|------|------|
| `src/jarvis/core/agent.py` | Core agent, `StarkNIMChatClient`, system prompt |
| `src/jarvis/core/handoff_workflow.py` | HandoffBuilder, triage, specialist agents |
| `src/jarvis/skills/skill_forge.py` | Load skills + `forge_skill` |
| `src/jarvis/core/subagents.py` | `load_subagent`, `sys_session_send` |
| `src/jarvis/core/soul.py` | Soul frontmatter → instructions |
| `src/jarvis/memory/memory_manager.py` | SQLite FTS5 |
| `src/jarvis/server/app.py` | FastAPI, SSE, sessions |
| `src/jarvis/cli.py` | TUI, server daemon |
| `src/jarvis/sync/github_sync.py` | Git push for skills/evolution |
| `src/jarvis/config/paths.py` | Workspace/data paths |
| `src/jarvis/config/models.py` | NIM basket, house-party |
| `skills/` | Root tools + `friday/`, `homer/`, `plato/` |
| `scratch/validate_handoffs.py` | Live handoff validation |
| `ARCHITECTURE.md` | Full architecture doc |

**MAF deps:** `agent-framework-core`, `agent-framework-openai`, and `agent-framework-orchestrations` from PyPI (`prerelease = "allow"` in `pyproject.toml` for orchestrations).

## Specialist roster (current codebase)

| Agent | Role | Tools / notes |
|-------|------|----------------|
| **Jarvis** | Butler, triage, handoffs | Root `skills/*.py`, `forge_skill` |
| **Homer** | Web research | `web_search`, `web_extract`, Playwright MCP (Node 18+) |
| **Friday** | Linux desktop hands | X11: `xdotool`, `scrot`, `wmctrl`; `display_env` guard |
| **Plato** | Code/repo analysis | `skills/plato/` |

Handoffs: `handoff_workflow.py`. Jarvis delegates; specialists return evidence; Jarvis answers in character. Preserve URLs, capture paths, and citations from specialist output.

## Harness rules

1. **Minimal diff** — match surrounding code; no unrelated refactors
2. **Skills** — `@tool` from `agent_framework`; hands specialists return structured JSON
3. **Friday contract** — orient → act → verify; kinetic tools `approval_mode="always_require"`
4. **Stark Core Matrix** — NIM failover in `agent.py`; basket in `models.py`; **no LLaMA**
5. **Skill forge** — `_exec_module_from_file` must register `sys.modules` before `exec_module` (dataclasses)
6. **Validation honesty** — score from last assistant message in `/history`, not partial SSE
7. **Commits** — only when Shaun asks; never commit secrets, `data/` logs, or scratch noise

## Common workflows

### Add a root skill
`skills/my_skill.py` with `@tool` → auto-loaded via `load_skills_from_dir(get_skills_dir())`.

### Add a subagent capability
Files in `skills/{name}/`, `{name}_soul.md`, `config.yaml`. New specialist → wire in `handoff_workflow.py`.

### Fix handoff routing
Edit `HANDOFF_TRIAGE_INSTRUCTIONS` + `HandoffBuilder` in `handoff_workflow.py`. Test: `tests/test_handoff_workflow.py`, `scratch/validate_handoffs.py`.

### Run / debug server
```bash
./run.sh                          # sync deps, build web, start CLI
python -m jarvis.cli server start # daemon :8008
python -m jarvis.cli server stop
```

### Run tests
```bash
pytest tests/test_handoff_workflow.py tests/test_skills_forge.py tests/test_computer_use.py -q
```

## Extensibility (patterns, not prescriptive)

When Shaun asks to extend Jarvis (new host, new specialist, sync, phone, etc.):

- **New specialist** — mirror Friday: `skills/{name}/`, soul playbooks, handoff registration
- **Host-specific tools** — subagent dirs or platform metadata on root skills; gate in loader
- **Multi-device** — separate `jarvis.db` per host; `github_sync.py` already syncs `skills/`
- **External experiments** — Shaun may have local repos (`~/Projects/termuxgemini`, `~/geminicli-jarvis-skill`); port patterns, don't fork architectures

Check `scratch/plans/` or user-linked Cursor plans for active roadmaps — not part of this skill.

## Further reading

- [reference.md](reference.md) — env vars, memory, evolution, validation details
