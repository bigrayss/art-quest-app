#!/usr/bin/env bash
# Start the Stage 1 prototype. Usage: ./run.sh [port]
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a
PORT="${1:-8000}"
exec python3 -m uvicorn artquest.main:app --host 127.0.0.1 --port "$PORT" --reload
