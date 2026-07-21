#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "JARVIS // Bootstrapping virtual environment..."
if command -v uv >/dev/null 2>&1; then
    uv venv .venv
else
    python3 -m venv .venv
fi
source .venv/bin/activate

echo "JARVIS // Installing dependencies from lockfile..."
if command -v uv >/dev/null 2>&1; then
    uv sync --no-group dev --all-extras
else
    pip install -U pip wheel -q
    pip install -e .[analysis]
fi

if [ ! -f .env ]; then
    echo "JARVIS // Creating .env from template..."
    cp .env.example .env
    if [ ! -z "$GITHUB_PERSONAL_ACCESS_TOKEN" ]; then
        sed -i "s/GITHUB_PERSONAL_ACCESS_TOKEN=your-github-pat-here/GITHUB_PERSONAL_ACCESS_TOKEN=$GITHUB_PERSONAL_ACCESS_TOKEN/" .env
    fi
fi

mkdir -p data

if [ ! -d .git ]; then
    echo "JARVIS // Initializing local git repository..."
    git init -b main
    
    echo "data/*.db" > .gitignore
    echo "data/*.db-journal" >> .gitignore
    echo "data/*.db-wal" >> .gitignore
    echo "data/*.db-shm" >> .gitignore
    echo ".venv/" >> .gitignore
    echo ".env" >> .gitignore
    echo "__pycache__/" >> .gitignore
    echo "*.pyc" >> .gitignore
    echo ".pytest_cache/" >> .gitignore
    
    git add .
    git commit -m "Initial commit of Jarvis workspace scaffold" || true
fi

echo "JARVIS // Configuring nightly subconscious cron jobs (Pray 2:00 AM, Dream 3:00 AM)..."
if command -v crontab >/dev/null 2>&1; then
    PRAY_CRON="0 2 * * * cd $SCRIPT_DIR && PYTHONPATH=$SCRIPT_DIR/src $SCRIPT_DIR/.venv/bin/python3 -m jarvis.evolution.subconscious pray >> $SCRIPT_DIR/data/subconscious_cron.log 2>&1"
    DREAM_CRON="0 3 * * * cd $SCRIPT_DIR && PYTHONPATH=$SCRIPT_DIR/src $SCRIPT_DIR/.venv/bin/python3 -m jarvis.evolution.subconscious dream >> $SCRIPT_DIR/data/subconscious_cron.log 2>&1"
    ( (crontab -l 2>/dev/null || true) \
        | grep -F -v "subconscious.py" \
        | grep -F -v "evolution.subconscious" \
        | grep -F -v "jarvis.evolution.subconscious" \
        ; echo "$PRAY_CRON" ; echo "$DREAM_CRON") | crontab -
else
    echo "JARVIS // crontab not available — skipping subconscious cron setup."
fi

echo "JARVIS // Bootstrapping completed successfully!"
if command -v node >/dev/null 2>&1; then
    echo "JARVIS // Node $(node --version) detected — Playwright MCP browser automation available via npx."
    echo "JARVIS // If browser tools fail, run: npx playwright install"
else
    echo "JARVIS // Warning: Node.js 18+ not found — install Node for Homer browser MCP tools."
fi
