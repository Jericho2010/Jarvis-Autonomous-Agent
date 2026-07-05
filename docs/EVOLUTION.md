# Subconscious Evolution

The Hermes Self-Evolution protocol allows Jarvis to stage new skills autonomously via nightly subconscious jobs, with human approval before promotion to live `skills/`.

## Overview

Two separate cron jobs registered by `setup.sh`:

| Job | Schedule | Module | Output |
|-----|----------|--------|--------|
| **Pray** | 2:00 AM | `python -m evolution.subconscious pray` | `data/evolution_logs/YYYY-MM-DD-pray.md`, optional skill in `skills_staging/pray/` |
| **Dream** | 3:00 AM | `python -m evolution.subconscious dream` | `data/evolution_logs/YYYY-MM-DD-dream.md`, optional skill in `skills_staging/dream/` |

Source: `src/evolution/subconscious/` (Pray: `pray.py`, Dream: `dream.py`).

## Pray workflow

1. Select saint of the day (`saint.py`)
2. Contemplative meditation via LLM
3. Structured JSON ideation for a new skill
4. Optional `forge_to_staging()` → writes to `skills_staging/pray/`
5. Narrow git sync of evolution artifacts (`sync.py`)

## Dream workflow

1. Ingest 24 hours of SQLite message history (`ingest.py`)
2. High-temperature "dream drift" reflection
3. Lateral skill ideation (deduped against same-night Pray output)
4. Optional staging → `skills_staging/dream/`
5. Git sync

## Human approval gate

Staged skills are **never** auto-promoted. Review in the TUI:

| Command | Action |
|---------|--------|
| `/evolve show` | List pending staged skills |
| `/evolve approve <name>` | Copy skill to live `skills/`, remove from staging |
| `/evolve reject <name>` | Move to `skills_staging/rejected/` |
| `/evolve archive` | Browse rejected skills |

Soul files (`*_soul.md`, `jarvis_soul/SKILL.md`) are **not** auto-rewritten by Pray or Dream.

## Manual run

```bash
PYTHONPATH=src .venv/bin/python3 -m evolution.subconscious pray
PYTHONPATH=src .venv/bin/python3 -m evolution.subconscious dream
PYTHONPATH=src .venv/bin/python3 -m evolution.subconscious all   # both
```

Logs append to `data/subconscious_cron.log` when run via cron.

## NIM failover

Pray and Dream use `StarkNIMChatClient` with `apply_primary_model(..., "house-party")` — the same Stark Core Matrix failover basket as the main agent.

## GitHub sync

Approved evolution artifacts sync to GitHub via `src/jarvis/sync/github_sync.py` when `GITHUB_PERSONAL_ACCESS_TOKEN` is set. Scope is narrow: `skills/`, evolution logs, and related manifests — not secrets or runtime data.

## Staging directories

```
skills_staging/
├── pray/           # Pray-staged modules awaiting review
├── dream/          # Dream-staged modules awaiting review
└── rejected/       # Rejected modules (archaeology)
```

Evolution logs: `data/evolution_logs/YYYY-MM-DD-pray.md` and `YYYY-MM-DD-dream.md`.

Manifest: `data/evolution_manifest.json`.

## Skill forge pipeline

Staging uses `src/evolution/subconscious/forge_pipeline.py` and `staging.py` to write Python skill modules without immediately loading them into the live agent. Promotion via `/evolve approve` moves the file to `skills/` where `skill_forge.py` picks it up on next load.
