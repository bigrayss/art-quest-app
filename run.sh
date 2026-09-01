#!/usr/bin/env bash
# Start the Stage 1 prototype. Usage: ./run.sh [port]
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a
PORT="${1:-8000}"
# prefer the project venv, so ./run.sh works without activating it first
PY_BIN="python3"
[ -x .venv/bin/python ] && PY_BIN=".venv/bin/python"
exec "$PY_BIN" -m uvicorn artquest.main:app --host 127.0.0.1 --port "$PORT" --reload
