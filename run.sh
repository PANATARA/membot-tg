#!/usr/bin/env bash
set -e

# Directory where script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if .venv exists
if [ ! -d ".venv" ]; then
    echo "📦 Создание виртуального окружения Python..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

# Run application
exec .venv/bin/python main.py "$@"
