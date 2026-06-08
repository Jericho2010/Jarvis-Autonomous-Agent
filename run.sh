#!/bin/bash
set -e

cd /home/shaun/jarvis

if [ ! -d .venv ]; then
    echo "JARVIS // Virtual environment not found. Running setup.sh first..."
    ./setup.sh
fi

source .venv/bin/activate
export PYTHONPATH=src:$PYTHONPATH
python3 -m jarvis.cli "$@"
