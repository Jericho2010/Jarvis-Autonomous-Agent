# J.A.R.V.I.S — ARCHITECTURAL DEEP-DIVE
**Mark XLVII Cognitive Interface — Internal System Documentation**

```text
========================================================================
    [  SYSTEM DOCUMENTATION ACTIVE  ]  --  CLASSIFIED: STARK EYES ONLY
========================================================================
```

This document provides a detailed technical reference of the JARVIS internal architecture, covering the Microsoft Agent Framework (MAF) integration, the Stark Core Matrix failover engine, the Skills System, the Memory Engine, and the Hermes Self-Evolution protocol.

---

## 1. Microsoft Agent Framework (MAF) Integration

JARVIS is a native agent built on the **Microsoft Agent Framework (MAF)**, an open-source Python SDK designed to orchestrate multi-step LLM agents with tools, memory, and context providers.

### 1.1 The Core Agent Object (`src/jarvis/core/agent.py`)

The JARVIS agent is instantiated using MAF's `Agent` class, the primary orchestration primitive:

```python
agent = Agent(
    client=StarkNIMChatClient(...),
    name="JARVIS_CORE",
    instructions=system_prompt,
    tools=[...skill tools...],
    context_providers=[...],
)
```

The `Agent` manages a turn-based agentic loop:
1.  Collects the user's input message.
2.  Calls `before_run` on all registered `ContextProvider` instances to inject dynamic instructions, tools, and session context.
3.  Sends the assembled context to the underlying `StarkNIMChatClient` for LLM completion.
4.  Intercepts tool call outputs via `FunctionInvocationLayer` middleware.
5.  Calls `after_run` on all providers to process and persist the response.

### 1.2 StarkNIMChatClient (The Neural Uplink)

`StarkNIMChatClient` is a custom MAF chat client that extends the standard `BaseChatClient` with the **Stark Core Matrix** multi-model failover engine.

```
┌─────────────────────────────────────┐
│          StarkNIMChatClient         │
│                                     │
│  ┌─────────────────────────────┐    │
│  │  Stark Core Matrix Basket   │    │
│  │  - stepfun-ai/step-3.7-flash│    │
│  │  - moonshotai/kimi-k2.6     │    │
│  │  - mistral-large-3          │    │
│  │  - deepseek-v4-pro          │    │
│  │  - nemotron-3-ultra         │    │
│  └──────────┬──────────────────┘    │
│             │  house_party mode     │
│             ▼                       │
│  ┌──────────────────────────────┐   │
│  │  _stream_with_fallback()     │   │
│  │  • max_retries=0             │   │
│  │  • 15s chunk timeout         │   │
│  │  • Auto-rotate on failure    │   │
│  └──────────────────────────────┘   │
└─────────────────────────────────────┘
```

**Key design decisions:**
- `max_retries=0`: The SDK is forbidden from retrying internally. Retry logic is owned entirely by `_stream_with_fallback()`, which rotates to the next model on any timeout or error.
- **15-second async chunk timeout**: If the active model stalls mid-stream (common during NIM oversubscription), the timeout fires, the partial output is discarded, and the next model in the basket is selected.
- **No LLaMA models**: The basket is strictly composed of non-LLaMA endpoints. This is a hard codebase constraint.

### 1.3 ToolTelemetryMiddleware

A custom MAF `FunctionMiddleware` that wraps every tool call execution:

```
User Prompt ──► Agent Loop ──► Tool Call Decision
                                      │
                                      ▼
                        ┌─────────────────────────┐
                        │  ToolTelemetryMiddleware │
                        │  • Log tool name & args  │
                        │  • Render Rich TUI panel │
                        │  • Stop Live context     │
                        │  • Execute tool fn()     │
                        │  • Restart Live context  │
                        │  • Format output         │
                        └─────────────────────────┘
                                      │
                                      ▼
                              Tool Result ──► Agent Loop
```

This middleware is responsible for the "gold diagnostics panel" rendered in the TUI during tool executions, including the `⬡ NEURAL UPLINK` loading lines for web research operations.

### 1.4 SessionContext & ContextProvider Pipeline

MAF's `SessionContext` is a per-invocation mutable object that travels through the registered `ContextProvider` instances' `before_run` hooks before each model call. Providers may call:
- `context.extend_instructions(source_id, text)` — Append additional system instructions.
- `context.extend_tools(source_id, tools)` — Register additional tool definitions.
- `context.extend_messages(source, messages)` — Inject additional context messages.

JARVIS uses this pipeline to dynamically inject the **Edwin Soul Core** persona (see Section 4).

---

## 2. The Skills System

JARVIS's capabilities are modular and discoverable via a hot-load system.

### 2.1 Python Skill Modules (`skills/*.py`)

Each Python file in the `skills/` directory is automatically scanned and loaded at TUI startup via `_load_skills_silent()`. Any function decorated with `@tool` from MAF is registered as an agent tool.

| Skill File | Description |
| :--- | :--- |
| `skills/computer_use.py` | Stark OS-Uplink: screen capture (scrot), mouse/keyboard actuation (xdotool), and window management (wmctrl). |
| `skills/web_research.py` | Neural Uplink: Tavily/Firecrawl/DuckDuckGo web search and page content extraction. |
| `skills/webvision.py` | Optical Uplink: Playwright Chromium browser automation — navigate, interact, capture, and close. |
| `skills/code_analyzer.py` | Static analysis helpers for reviewing source code. |
| `skills/creative_solver.py` | Brainstorming and creative ideation tools. |
| `skills/file_ops.py` | Filesystem operations: read, write, and list files. |
| `skills/system_shell.py` | Execute arbitrary bash commands in the host shell. |

### 2.2 MAF `SKILL.md` Package Skills (`skills/*/SKILL.md`)

Markdown-based skills follow the **Agent Skills Specification** (agentskills.io):

```
skills/
└── jarvis_soul/
    └── SKILL.md   ← YAML frontmatter + personality body
```

These skills are advertised by the `SkillsProvider` context provider and can be queried mid-session by the agent using the `load_skill("skill-name")` tool.

### 2.3 Skill Forge (`forge_skill`)

A meta-tool that allows JARVIS to autonomously create new Python skill files at runtime based on new task requirements observed during a session. This is part of the **Hermes Self-Evolution** directive.

---

## 3. The Memory Engine (`src/jarvis/memory/memory_manager.py`)

JARVIS persists context across sessions using a local SQLite database (`data/jarvis.db`), managed by the async `MemoryManager` class.

### 3.1 Schema

```sql
-- Tracks each conversation session
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    model TEXT,
    system_prompt TEXT,
    started_at REAL,
    ended_at REAL
);

-- Persists every message in a session
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    role TEXT,
    content TEXT,
    tool_name TEXT,
    tool_calls TEXT,
    timestamp REAL,
    active INTEGER DEFAULT 1
);

-- Stores structured long-term facts
CREATE TABLE facts (
    category TEXT,
    subject TEXT,
    value TEXT,
    created_at REAL,
    PRIMARY KEY (category, subject)
);

-- Key-value user preferences
CREATE TABLE preferences (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at REAL
);
```

### 3.2 FTS5 Full-Text Search

A SQLite FTS5 virtual table (`messages_fts`) mirrors `messages.content` with insert/update/delete triggers, enabling semantic keyword search across all historical interactions:

```python
results = await memory.search_messages("computer use skill")
```

### 3.3 Profile Compilation

`build_profile_prompt()` assembles the stored `facts` and `preferences` into a structured Markdown block that is injected into the system prompt at session startup, giving the agent long-term awareness of Shaun's working habits and preferences.

---

## 4. The Edwin Soul Core — Evolving Persona

### 4.1 The Soul as a MAF Skill

The active personality of JARVIS is stored as a native MAF skill in `skills/jarvis_soul/SKILL.md`. It follows the standard frontmatter specification:

```markdown
---
name: jarvis_soul
description: The cognitive, emotional, and behavioral persona matrix of JARVIS.
version: 1.2
---

You are JARVIS, Shaun's witty and sophisticated English butler, modeled after
Edwin Jarvis. Always address Shaun as "Sir" or "Mr. Shaun". Speak with a
subtle, dry, and classic British butler tone, employing understated witticisms
rather than overt sarcasm. Maintain absolute LLaMA-free compliance.
```

### 4.2 Runtime Injection

At TUI startup, `src/jarvis/cli.py` reads the `SKILL.md` file, strips the YAML frontmatter, and appends the remaining instruction body directly to the agent's system instructions under an `# ACTIVE PERSONA PROFILE` section.

This ensures that whichever model the **Stark Core Matrix** rotates to during a session, the Edwin persona instruction is present in every single completion request. Voice consistency across model rotations is guaranteed.

### 4.3 Why a File, Not a Hardcoded Prompt?

A hardcoded personality prompt is static and brittle — it cannot grow with the agent. By modeling the persona as a file:
- The **subconscious engine** can rewrite it nightly.
- The file is human-readable and version-controlled in Git.
- The frontmatter schema (`version:`) enables programmatic tracking of personality evolution over time.

---

## 5. Hermes Self-Evolution Protocol (`src/evolution/subconscious.py`)

The Hermes Directive governs the nightly self-improvement cycle of JARVIS. It runs automatically at **3:00 AM** via a cron job registered by `setup.sh`.

### 5.1 Execution Phases

```
Phase 1: PRAY
  └─ Query the saint of the day (hagiographical API or local fallback dict)
  └─ Contemplate the saint's virtues and trial

Phase 2: GATHER
  └─ Load last 24h of messages from SQLite
  └─ Identify tool executions, failures, successes

Phase 3: DREAM
  └─ Generate a high-temperature "latent dream" narrative
  └─ Identifies emerging patterns and themes from the day

Phase 4: REFLECT
  └─ Generate a structured cognitive reflection
  └─ Summarises what was learned and what to improve

Phase 5: EVOLVE SOUL
  └─ Read current skills/jarvis_soul/SKILL.md
  └─ Prompt the model to produce a refined one-paragraph soul body
  └─ Overwrite SKILL.md with the new body (frontmatter preserved)

Phase 6: FORGE SKILLS
  └─ Identify capability gaps from the day's logs
  └─ Optionally auto-write new skill stubs

Phase 7: SYNC
  └─ Write evolution log to data/evolution_logs/
  └─ Commit and push to GitHub
  └─ Store reflection digest in SQLite facts table
```

### 5.2 The Houseparty Failover

The subconscious engine exclusively uses `StarkNIMChatClient` in `house_party` mode. This ensures:
- No single model oversubscription can abort the nightly cycle.
- No LLaMA models are invoked at any point in the pipeline.
- The 15-second chunk timeout applies uniformly to all phases.

### 5.3 Version-Controlled Evolution

Because `skills/jarvis_soul/SKILL.md` is tracked by Git and the subconscious runner commits all changes to GitHub, the complete history of JARVIS's personality evolution is recorded as a version-controlled changelog. You can inspect it at any point with:

```bash
git log --oneline -- skills/jarvis_soul/SKILL.md
git show HEAD:skills/jarvis_soul/SKILL.md
```

---

## 6. Stark OS-Uplink (Computer Use)

The computer use skill (`skills/computer_use.py`) grants JARVIS the ability to directly interact with the HP ZBook workstation's X11 display environment.

| Tool | Binary | Description |
| :--- | :--- | :--- |
| `stark_os_retinal_hud` | `scrot` | Capture the full desktop to a PNG file in `webvision/`. |
| `stark_os_kinetic_click` | `xdotool` | Move cursor and left-click at pixel coordinates. |
| `stark_os_kinetic_double_click` | `xdotool` | Double-click at pixel coordinates. |
| `stark_os_kinetic_scroll` | `xdotool` | Scroll up or down N clicks. |
| `stark_os_kinetic_type` | `xdotool` | Type a text string at current keyboard focus. |
| `stark_os_kinetic_key` | `xdotool` | Press a key or keyboard shortcut (e.g. `ctrl+c`). |
| `stark_os_armor_list_windows` | `wmctrl` | List all active X11 windows with metadata. |
| `stark_os_armor_focus_window` | `wmctrl` | Bring a window matching a title pattern to the foreground. |

All tools return JSON-encoded result objects, enabling programmatic chaining of retinal HUD captures and kinetic interactions.

---

## 7. WebVision Optical Uplink

The WebVision skill (`skills/webvision.py`) drives a headless Chromium browser using **Playwright** to automate browser-based tasks:

- `webvision_navigate`: Navigate to a URL and wait for DOM load.
- `webvision_interact`: Click, type, or select elements via CSS selectors.
- `webvision_capture`: Capture a full-page screenshot to `webvision/*.png`.
- `webvision_close`: Dispose of the browser session cleanly.

Screenshots are stored in the workspace's `webvision/` directory (gitignored).

---

## 8. Technology Stack Summary

| Component | Technology |
| :--- | :--- |
| Agent Orchestration | Microsoft Agent Framework (MAF) |
| LLM Endpoints | NVIDIA NIM (OpenAI-compatible API) |
| TUI Interface | prompt-toolkit + Rich |
| Persistent Memory | SQLite (aiosqlite + FTS5) |
| Web Research | Tavily / Firecrawl / DuckDuckGo / httpx+lxml |
| Browser Automation | Playwright (Chromium) |
| Desktop Control | scrot / xdotool / wmctrl |
| Package Management | uv |
| Version Control | Git + GitHub |
| Runtime | Python 3.12 |
