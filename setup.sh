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

echo "JARVIS // Installing dependencies in editable mode..."
if command -v uv >/dev/null 2>&1; then
    uv pip install -e .
else
    pip install -U pip wheel -q
    pip install -e .
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

echo "JARVIS // Configuring nightly subconscious cron job (3:00 AM)..."
if command -v crontab >/dev/null 2>&1; then
    CRON_CMD="0 3 * * * cd $SCRIPT_DIR && $SCRIPT_DIR/.venv/bin/python3 src/evolution/subconscious.py >> $SCRIPT_DIR/data/subconscious_cron.log 2>&1"
    (crontab -l 2>/dev/null | grep -F -v "src/evolution/subconscious.py" ; echo "$CRON_CMD") | crontab -
else
    echo "JARVIS // crontab not available — skipping subconscious cron setup."
fi

echo "JARVIS // Bootstrapping completed successfully!"
