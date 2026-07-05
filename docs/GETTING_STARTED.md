# Getting Started

This guide covers installation, first run, and the two primary interfaces: the TUI and the Web HUD.

## Prerequisites

- **Python 3.10+** (3.12 recommended)
- **`uv`** package manager — [install instructions](https://docs.astral.sh/uv/getting-started/installation/)
- **Node.js 18+** (optional but recommended for Homer browser automation via Playwright MCP)
- **Linux desktop tools** (optional, for Friday desktop automation on X11):
  - `xdotool`, `scrot`, `wmctrl`

No sibling repositories are required. Microsoft Agent Framework packages install from PyPI.

On GitHub Codespaces or other headless hosts (no `DISPLAY`), Friday desktop tools are skipped at startup. The TUI, API server, and Homer browser MCP still work.

## Installation

Run the bootstrap script to create the virtual environment, install dependencies, and register nightly subconscious cron jobs (Pray 2:00 AM, Dream 3:00 AM):

```bash
chmod +x setup.sh run.sh
./setup.sh
```

Copy and populate your environment file:

```bash
cp .env.example .env
# Edit .env — at minimum set NVIDIA_API_KEY
```

See [CONFIGURATION.md](CONFIGURATION.md) for all environment variables.

## Running Jarvis

### Full stack (recommended)

`run.sh` syncs Python deps, builds the Web HUD, restarts the API server if needed, and launches the TUI:

```bash
./run.sh
```

The Web HUD is served at **http://127.0.0.1:8008** once the server is running.

### TUI only

```bash
source .venv/bin/activate
export PYTHONPATH=src
python -m jarvis.cli
```

### Server daemon

```bash
python -m jarvis.cli server start   # background uvicorn on port 8008 (or next free port)
python -m jarvis.cli server status  # check PID and port
python -m jarvis.cli server stop      # graceful shutdown
```

Server state is tracked in `data/server.pid`.

### Web HUD development

For hot-reload during frontend work:

```bash
cd web && npm install && npm run dev   # Vite on :5173, probes API on :8008
```

See [WEB_HUD.md](WEB_HUD.md) for production build and UI details.

## First session

1. Start with `./run.sh`.
2. Type a prompt and press **Enter** to submit. Use **Alt+Enter** for multiline input.
3. Try `/help` for the command manual.
4. Try `/agent homer` then ask a web research question to smoke-test the Homer specialist.
5. Open **http://127.0.0.1:8008** in a browser — the Web HUD mirrors the same session via SSE.

## TUI slash commands

| Command | Description |
|---------|-------------|
| `/help` | Show command manual |
| `/new` | Start a fresh dialogue session (finalizes the previous session's memory) |
| `/switch [id\|index]` | Switch to an existing session |
| `/agent <jarvis\|homer\|friday\|plato>` | Switch active session agent |
| `/voicemode [on\|off]` | Toggle spoken butler voice (NIM TTS) |
| `/models` | List available cognitive models |
| `/model <name\|index>` | Set primary model or Stark Core Matrix routing |
| `/subagents` | List cognitive sub-agent profiles |
| `/skills` | List loaded skill modules |
| `/evolve [approve\|reject\|archive\|show]` | Review staged subconscious skills |
| `/tasks` | Show implementation task backlog |
| `/clear` | Clear the screen |
| `/exit` | Exit TUI |

## Headless vs desktop

| Capability | Desktop (X11) | Headless / Codespaces |
|------------|---------------|------------------------|
| TUI + API server | Yes | Yes |
| Web HUD | Yes | Yes |
| Homer web research + Playwright MCP | Yes (Node required) | Yes (Node required) |
| Friday desktop automation | Yes | Skipped |
| Voice mode (NIM speech) | Yes | Yes (with `NVIDIA_API_KEY`) |

Startup dependency checks run via `src/jarvis/core/system_deps.py` and log warnings without blocking startup.

## Next steps

- [CONFIGURATION.md](CONFIGURATION.md) — environment variables, paths, cron
- [SKILLS.md](SKILLS.md) — subagents, tools, skill forge
- [API.md](API.md) — REST and SSE reference
- [ARCHITECTURE.md](ARCHITECTURE.md) — full technical deep-dive
