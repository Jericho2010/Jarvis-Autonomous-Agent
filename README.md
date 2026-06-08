# Jarvis — The AI Co-Builder & Companion

Jarvis is a unified, lightweight Linux agent designed for real-time pair-programming, system automation, and subconscious capability development. It combines:
1. **Microsoft Agent Framework** for core agent-loop orchestration and tools routing.
2. **prompt-toolkit + rich** for a single-lane interactive TUI.
3. **SQLite FTS5 Memory Engine** for message indexing and facts.
4. **Nightly Subconscious Evolution (Dream/Pray/Reflect)** for self-improvement and autonomous skill-writing.

## Getting Started

### Prerequisites
- Python 3.10+
- `uv` package manager (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

### Installation
Run the bootstrap script to create the virtual environment, install dependencies, and register the nightly 3:00 AM subconscious cron job:
```bash
chmod +x setup.sh run.sh
./setup.sh
```

Ensure you populate your `.env` file with the correct NVIDIA NIM credentials:
```env
NVIDIA_API_KEY=nvapi-...
GITHUB_PERSONAL_ACCESS_TOKEN=your_token
```

### Running the TUI
Start the session REPL:
```bash
./run.sh
```

Inside the CLI, you can type slash commands:
- `/help` — List available slash commands.
- `/skills` — Show hot-loaded skill modules.
- `/clear` — Clear the screen.
- `/new` — Start a fresh dialogue session.

---

## Build Log

- **2026-06-08** - Initial Scaffolding - Created pyproject.toml, .env.example, setup.sh, run.sh, and README.md.
