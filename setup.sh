#!/bin/bash
set -e

echo "JARVIS // Bootstrapping virtual environment..."
uv venv .venv
source .venv/bin/activate

echo "JARVIS // Installing dependencies in editable mode..."
uv pip install -e .

if [ ! -f .env ]; then
    echo "JARVIS // Creating .env from template..."
    cp .env.example .env
    # Pull token from user environment if exists
    if [ ! -z "$GITHUB_PERSONAL_ACCESS_TOKEN" ]; then
        sed -i "s/GITHUB_PERSONAL_ACCESS_TOKEN=your-github-pat-here/GITHUB_PERSONAL_ACCESS_TOKEN=$GITHUB_PERSONAL_ACCESS_TOKEN/" .env
    fi
fi

# Ensure data directory exists
mkdir -p data

# Initialize Git
if [ ! -d .git ]; then
    echo "JARVIS // Initializing local git repository..."
    git init -b main
    
    # Create Git ignore
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

# Cron Setup
echo "JARVIS // Configuring nightly subconscious cron job (3:00 AM)..."
CRON_CMD="0 3 * * * cd /home/shaun/jarvis && /home/shaun/jarvis/.venv/bin/python3 src/evolution/subconscious.py >> /home/shaun/jarvis/data/subconscious_cron.log 2>&1"
(crontab -l 2>/dev/null | grep -F -v "src/evolution/subconscious.py" ; echo "$CRON_CMD") | crontab -

echo "JARVIS // Bootstrapping completed successfully!"
