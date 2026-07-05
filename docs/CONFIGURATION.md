# Configuration

Jarvis reads configuration from environment variables (`.env` at the repo root) and optional path overrides.

## Required

| Variable | Purpose |
|----------|---------|
| `NVIDIA_API_KEY` | NVIDIA NIM chat endpoints and NIM hosted speech (gRPC TTS/STT) |

## GitHub sync (optional)

| Variable | Purpose |
|----------|---------|
| `GITHUB_PERSONAL_ACCESS_TOKEN` | Push approved skills and evolution logs to GitHub via `src/jarvis/sync/github_sync.py` |

## Path overrides

| Variable | Default | Purpose |
|----------|---------|---------|
| `JARVIS_WORKSPACE_ROOT` | Repo root | Override workspace root |
| `JARVIS_DATA_DIR` | `{workspace}/data` | SQLite, logs, session files |
| `JARVIS_DB_PATH` | `{data}/jarvis.db` | SQLite database location |
| `JARVIS_PORT` | `8008` | Preferred API server port (CLI scans upward if occupied) |

Path resolution is implemented in `src/jarvis/config/paths.py`.

## Web research (optional)

Homer falls back to keyless tools when these are unset:

| Variable | Purpose |
|----------|---------|
| `TAVILY_API_KEY` | Premium web search via Tavily API |
| `FIRECRAWL_API_KEY` | Premium page extraction via Firecrawl |

Without keys, Homer uses DuckDuckGo (`ddgs`) and local `httpx` + `lxml` scraping.

## Voice mode

Voice uses the same `NVIDIA_API_KEY` via NIM hosted speech (gRPC). Defaults align with `src/jarvis/config/voice.py`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `NIM_SPEECH_GRPC_URI` | `grpc.nvcf.nvidia.com:443` | NIM speech gRPC endpoint |
| `NIM_TTS_FUNCTION_ID` | (built-in UUID) | TTS function ID |
| `NIM_ASR_FUNCTION_ID` | (built-in UUID) | STT function ID |
| `JARVIS_BUTLER_VOICE` | `Magpie-Multilingual.EN-US.Ray.Calm` | TTS voice name |
| `JARVIS_BUTLER_LANGUAGE` | `en-US` | Speech language |
| `JARVIS_VOICE_RATE_SCALE` | `0.92` | Playback rate (lower = slower, more measured delivery) |

Voice mode is **off by default** at server startup. Enable per session via `/voicemode on` (TUI) or the Web HUD voice toggle.

Speech client dependency: `nvidia-riva-client` (installed automatically by `run.sh`).

## System dependencies

### Python packages

Managed via `pyproject.toml` and installed with `uv sync` or `pip install -e .`. Key runtime deps:

- `agent-framework-core`, `agent-framework-openai`, `agent-framework-orchestrations` (MAF)
- `fastapi`, `uvicorn`, `aiosqlite`, `prompt-toolkit`, `rich`
- `ddgs`, `tavily-python`, `firecrawl-py` (web research)
- `nvidia-riva-client` (voice)
- `numpy`, `nltk`, `scikit-learn` (text analysis skills)

### Node.js (Homer)

- Node 18+ and `npx` for `@playwright/mcp`
- Run `npx playwright install` if browser tools fail

### Linux desktop (Friday)

- `xdotool`, `scrot`, `wmctrl` on X11 with `DISPLAY` set
- Skipped automatically in headless environments (`GITHUB_CODESPACES=true` or no `DISPLAY`)

## Nightly subconscious cron

Registered by `setup.sh`:

| Job | Schedule | Command |
|-----|----------|---------|
| Pray | 2:00 AM | `PYTHONPATH=src .venv/bin/python3 -m evolution.subconscious pray` |
| Dream | 3:00 AM | `PYTHONPATH=src .venv/bin/python3 -m evolution.subconscious dream` |

Logs append to `data/subconscious_cron.log`.

Manual run:

```bash
PYTHONPATH=src .venv/bin/python3 -m evolution.subconscious all
```

See [EVOLUTION.md](EVOLUTION.md) for the full subconscious workflow.

## Example `.env`

```env
NVIDIA_API_KEY=nvapi-...
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...

# Optional web research
# TAVILY_API_KEY=tvly-...
# FIRECRAWL_API_KEY=fc-...

# Optional path overrides
# JARVIS_WORKSPACE_ROOT=
# JARVIS_DATA_DIR=
# JARVIS_DB_PATH=
# JARVIS_PORT=8008

# Optional voice overrides
# JARVIS_BUTLER_VOICE=Magpie-Multilingual.EN-US.Ray.Calm
# JARVIS_BUTLER_LANGUAGE=en-US
# JARVIS_VOICE_RATE_SCALE=0.92
```
