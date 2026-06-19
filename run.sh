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
python3 -m jarvis.cli "$@"
