# Skills and Subagents

Jarvis capabilities are modular Python tools loaded at runtime, organized into root skills (Jarvis core) and specialist subagent directories.

## Directory layout

```
skills/
├── jarvis_soul/
│   └── SKILL.md              # Edwin butler persona (MAF skill package)
├── file_ops.py               # read/write/list files
├── system_shell.py           # execute_bash
├── memory_recall.py          # recall_past_chats (FTS5 search)
├── text_associator.py        # semantic text association (scikit-learn)
├── metaphor_analyzer.py      # metaphor analysis
├── homer/
│   ├── config.yaml
│   ├── homer_soul.md
│   └── web_research.py       # web_search, web_extract
├── friday/
│   ├── config.yaml
│   ├── friday_soul.md
│   ├── computer_use.py       # Stark OS-Uplink (X11 desktop)
│   └── app_launcher.py       # discover/launch GUI apps
└── plato/
    ├── config.yaml
    ├── plato_soul.md
    ├── code_analyzer.py      # static analysis helpers
    └── repo_reader.py        # repository reading tools
```

Skill loader: `src/jarvis/skills/skill_forge.py` (`load_skills_from_dir`, `forge_skill`).

## Specialist roster

| Agent | Codename | Role | Tools |
|-------|----------|------|-------|
| **Jarvis** | Butler / triage | Default chat, handoff coordination | Root `skills/*.py`, `forge_skill`, `recall_past_chats` |
| **Homer** | Neural Uplink | Web research + browser automation | `web_search`, `web_extract`, `@playwright/mcp` |
| **Friday** | Stark OS-Uplink | Linux desktop hands | `computer_use.py`, `app_launcher.py` |
| **Plato** | Code Matrix | Repo analysis and code review | `code_analyzer.py`, `repo_reader.py` |

### Homer — web research

- **Search:** Tavily API (if `TAVILY_API_KEY` set) → DuckDuckGo fallback
- **Extract:** Firecrawl (if `FIRECRAWL_API_KEY` set) → local httpx + lxml fallback
- **Browser:** Playwright MCP subprocess (`npx -y @playwright/mcp@latest --headless`)

### Friday — desktop automation

| Tool | Binary | Approval |
|------|--------|----------|
| `stark_os_retinal_hud` | `scrot` | No |
| `stark_os_kinetic_click` | `xdotool` | **Required** |
| `stark_os_kinetic_double_click` | `xdotool` | **Required** |
| `stark_os_kinetic_scroll` | `xdotool` | **Required** |
| `stark_os_kinetic_type` | `xdotool` | **Required** |
| `stark_os_kinetic_key` | `xdotool` | **Required** |
| `stark_os_armor_list_windows` | `wmctrl` | No |
| `stark_os_armor_list_apps` | `.desktop` index | No |
| `stark_os_armor_launch_app` | gtk-launch/gio | **Required** |
| `stark_os_armor_focus_window` | `wmctrl` | **Required** |

Kinetic tools use `approval_mode="always_require"`. The workflow pauses and emits SSE `approval_required`; approve via Web HUD or API.

Captures land in `webvision/` and are served at `/v1/captures/{filename}`.

Headless guard: `src/jarvis/core/display_env.py` — Friday tools are unavailable without X11.

### Plato — code analysis

Handles repo reading, static analysis, skill audits, and architecture critique when Jarvis delegates.

## Digital Hands handoffs

Default Jarvis chat runs a MAF **HandoffBuilder** workflow (`src/jarvis/core/handoff_workflow.py`):

```
Jarvis ──→ Homer   (web + Playwright MCP)
       ──→ Friday  (X11 desktop)
       ──→ Plato   (repo/code)
       ←── specialists return to Jarvis
```

Triage rules are in `HANDOFF_TRIAGE_INSTRUCTIONS` within `handoff_workflow.py`. Jarvis preserves evidence (URLs, capture paths, citations) from specialist output.

Direct `/agent homer|friday|plato` bypasses the handoff workflow and runs a single specialist agent.

## Soul files

Each agent has a compiled soul markdown file with YAML frontmatter:

| Agent | Soul file |
|-------|-----------|
| Jarvis | `skills/jarvis_soul/SKILL.md` |
| Homer | `skills/homer/homer_soul.md` |
| Friday | `skills/friday/friday_soul.md` |
| Plato | `skills/plato/plato_soul.md` |

Compiled via `src/jarvis/core/soul.py` (`load_compiled_soul`). Subagent config (model, metadata) lives in `skills/{name}/config.yaml`.

Soul files are **not** auto-rewritten by subconscious jobs.

## Skill forge

`forge_skill(name, code, test_command?)` in `src/jarvis/skills/skill_forge.py`:

1. Writes `skills/{name}.py`
2. Compiles and optionally runs a test command
3. Load-verifies the new module

Used by Jarvis at runtime and by subconscious evolution staging.

## Staging and `/evolve`

Nightly Pray/Dream jobs may stage new skills under `skills_staging/`:

```
skills_staging/
├── pray/       # Pray-staged skills
├── dream/      # Dream-staged skills
└── rejected/   # Rejected skills (archaeology)
```

TUI commands:

| Command | Action |
|---------|--------|
| `/evolve show` | List staged skills |
| `/evolve approve <name>` | Promote to live `skills/` |
| `/evolve reject <name>` | Move to `skills_staging/rejected/` |
| `/evolve archive` | List rejected skills |

See [EVOLUTION.md](EVOLUTION.md) for the full subconscious protocol.

## Adding a new root skill

Create `skills/my_skill.py` with MAF `@tool` decorators. Root skills auto-load via `load_skills_from_dir(get_skills_dir())`.

## Adding a new specialist

1. Create `skills/{name}/` with `{name}_soul.md`, `config.yaml`, and tool modules.
2. Wire handoff registration in `src/jarvis/core/handoff_workflow.py`.
3. Add to `/agent` and `switch-agent` valid agent lists if needed.

## Memory recall

`recall_past_chats(query, limit=8)` in `skills/memory_recall.py` searches all sessions via SQLite FTS5. Jarvis uses this when Shaun references past work or decisions.
