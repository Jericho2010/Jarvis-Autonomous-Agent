# Jarvis Harness Reference

## Environment variables

| Variable | Purpose |
|----------|---------|
| `NVIDIA_API_KEY` | NIM chat + voice |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | Evolution/skills sync |
| `JARVIS_WORKSPACE_ROOT` | Override repo root |
| `JARVIS_DATA_DIR` / `JARVIS_DB_PATH` | SQLite and data location |
| `JARVIS_PORT` | Server port (default 8008) |
| `TAVILY_API_KEY` | Optional Homer premium search |
| `FIRECRAWL_API_KEY` | Optional Homer premium extract |
| `JARVIS_BUTLER_VOICE` | NIM TTS voice override |
| `JARVIS_VOICE_RATE_SCALE` | TTS playback rate (default 0.92) |

See `.env.example` and `docs/CONFIGURATION.md` for full list.

## Server and clients

| Action | Command |
|--------|---------|
| Full stack | `./run.sh` |
| Server start/stop | `python -m jarvis.cli server start\|stop` |
| TUI | `python -m jarvis.cli` |
| Web HUD | `http://127.0.0.1:8008` (needs `web/dist`) |

SSE: clients pass `client_id` (`tui`, `web`) to avoid echo on mirrored prompts.

## Skill loading

```
skills/{dir}/*.py
  → load_skills_from_dir()
  → _exec_module_from_file()  # sys.modules registration required
  → FunctionTool instances
```

`forge_skill(name, code, test_command?)` writes `skills/{name}.py`, compiles, optional test, load-verifies.

## Handoff graph (as implemented)

```text
Jarvis
  ├─→ Homer   (web + Playwright MCP)
  ├─→ Friday  (X11 desktop)
  └─→ Plato   (repo)
  ←── specialists return to Jarvis
```

Triage text: `HANDOFF_TRIAGE_INSTRUCTIONS` in `handoff_workflow.py`.

## Friday (desktop hands)

- Tools: `skills/friday/computer_use.py`, `app_launcher.py`
- Guard: `src/jarvis/core/display_env.py` — X11 + `xdotool`
- Soul playbooks: recon, launch, kinetic, media recon

## Homer (web)

- `skills/homer/web_research.py`
- Playwright: `src/jarvis/core/playwright_mcp.py` (Node 18+, `npx @playwright/mcp`)

## Memory

- DB: `data/jarvis.db` (override via `JARVIS_DB_PATH`)
- FTS5 on messages; `facts`, `preferences` tables
- `skills/memory_recall.py` → `recall_past_chats`
- Session finalize: `src/jarvis/memory/extractor.py` → summary + durable facts on `/new`
- Rehydration: `format_rehydration_block()` restores last 12 turns after server restart
- Profile: `build_profile_prompt()` injects prefs, recent summaries, facts at session start

## Voice mode

- NIM gRPC TTS/STT: `src/jarvis/voice/nim_speech.py`
- Config: `src/jarvis/config/voice.py` (default voice Ray.Calm, rate 0.92)
- TUI: `/voicemode on|off`
- API: `/v1/voice/status`, `/mode`, `/tts`, `/stt`
- Web: `web/src/hooks/useVoiceMode.ts`
- Off by default at server boot; preference key `voice_mode_enabled`

## Subconscious / evolution

- `src/evolution/subconscious/` — Pray 2am, Dream 3am (PC cron via `setup.sh`)
- Staging: `skills_staging/`; TUI `/evolve approve|reject`
- Push: `src/jarvis/sync/github_sync.py` → `skills/`, evolution logs

## Validation harness

`scratch/validate_handoffs.py`:

- Ground truth: `wmctrl`, `xdotool`, `scrot` on Linux desktop
- API: `POST /v1/sessions`, `POST .../chat`, `GET .../history`
- Score final assistant reply; configurable turn timeout

## Hard constraints

- No LLaMA in NIM basket
- `scikit-learn` required for `skills/text_associator.py`
- `agent-framework-*` packages from PyPI (orchestrations may be pre-release)

## Useful tests

```bash
pytest tests/test_handoff_workflow.py -q
pytest tests/test_skills_forge.py -q
pytest tests/test_computer_use.py -q
pytest tests/test_server.py -q
```

## Shaun's local experiment repos (optional port sources)

| Path | Contents |
|------|----------|
| `~/Projects/termuxgemini` | Termux:API bridge, voice widget experiments |
| `~/geminicli-jarvis-skill` | Prior Gemini/Jarvis CLI, vision_nav, skills |

Use when Shaun explicitly asks to port phone or legacy patterns — not default context.

## Active roadmaps

Task-specific plans may live in:

- `scratch/plans/` (repo)
- `~/.cursor/plans/` (Cursor)

Read only when the user or task references them.
