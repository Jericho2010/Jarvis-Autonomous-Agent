#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d .venv ]; then
    echo "JARVIS // Virtual environment not found. Running setup.sh first..."
    ./setup.sh
fi

source .venv/bin/activate
export PYTHONPATH=src:$PYTHONPATH

mkdir -p data

# Install/update Python deps (e.g. nvidia-riva-client for voice mode)
echo "JARVIS // Syncing Python dependencies..."
pip install -U pip wheel -q 2>/dev/null || true
if command -v uv >/dev/null 2>&1; then
    uv pip install -e . -q
else
    pip install -e . -q
fi

# Verify speech dependency required for /voicemode
if ! python3 -c "import riva.client" 2>/dev/null; then
    echo "JARVIS // Installing NVIDIA Riva speech client..."
    pip install "nvidia-riva-client>=2.19.0" -q
fi
python3 -c "import riva.client; print('JARVIS // Speech client (riva): OK')"

# web/dist is not committed — always rebuild so git pull / merge changes appear in the HUD
if command -v npm >/dev/null 2>&1 && [ -d web ] && [ -f web/package.json ]; then
    echo "JARVIS // Building Web HUD..."
    (cd web && npm install --silent && npm run build)
else
    echo "JARVIS // WARNING: npm not found — Web HUD may be stale. Install Node.js or run: (cd web && npm run build)"
fi

# Stop any lingering API server so backend + static UI reload after updates
if [ -f data/server.pid ]; then
    echo "JARVIS // Restarting API server to load latest code..."
    python3 -m jarvis.cli server stop 2>/dev/null || true
    sleep 1
fi

python3 -m jarvis.cli "$@"
