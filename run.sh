#!/usr/bin/env bash
# Start the app. Usage: ./run.sh [port]
#
#   ./run.sh                 只给这台机器用（127.0.0.1）
#   HOST=0.0.0.0 ./run.sh    同一个 wifi 下的手机 / iPad 也能打开
#
# 绑 0.0.0.0 就是把画画和已经收上来的作品暴露给整个局域网，所以要自己开，
# 不做默认。出了局域网（真的给别人用）要的是 HTTPS + 一个域名，不是这个脚本。
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a
PORT="${1:-8000}"
HOST="${HOST:-127.0.0.1}"
# prefer the project venv, so ./run.sh works without activating it first
PY_BIN="python3"
[ -x .venv/bin/python ] && PY_BIN=".venv/bin/python"

if [ "$HOST" != "127.0.0.1" ] && [ "$HOST" != "localhost" ]; then
  LAN="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [ -n "${LAN:-}" ] && echo "手机上打开：http://${LAN}:${PORT}/"
fi
exec "$PY_BIN" -m uvicorn artquest.main:app --host "$HOST" --port "$PORT" --reload
