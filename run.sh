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

# Rebuild Web HUD when sources are newer than the bundled dist (dist is not committed)
if command -v npm >/dev/null 2>&1 && [ -d web ] && [ -f web/package.json ]; then
    NEED_BUILD=0
    if [ ! -f web/dist/index.html ]; then
        NEED_BUILD=1
    elif find web/src -type f -newer web/dist/index.html -print -quit 2>/dev/null | grep -q .; then
        NEED_BUILD=1
    fi
    if [ "$NEED_BUILD" -eq 1 ]; then
        echo "JARVIS // Building Web HUD..."
        (cd web && npm install --silent && npm run build)
    fi
fi

python3 -m jarvis.cli "$@"
