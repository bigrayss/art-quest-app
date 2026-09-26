#!/usr/bin/env bash
# Start the app. Usage: ./run.sh [port]
#
#   ./run.sh                 只给这台机器用（127.0.0.1）
#   HOST=0.0.0.0 ./run.sh    同一个 wifi 下的手机 / iPad 也能打开
#
# 绑 0.0.0.0 就是把画画和已经收上来的作品暴露给整个局域网，所以要自己开，
# 不做默认。
#
# **给 iPad 用的话，别走这条路，走 Tailscale**（见 README「装到 iPad 上」）：
#   tailscale serve --bg --https=443 http://127.0.0.1:8010
# 然后 iPad 上开 https://<机器名>.<tailnet>.ts.net。那是**真 HTTPS**，
# 所以 Service Worker 能注册——局域网 http 下它根本不注册，
# 「装到主屏」装得上但断网就是白屏。而且默认只有自己 tailnet 里的设备看得见，
# 不像 0.0.0.0 那样把孩子的画摊给整个 wifi。这时 HOST 保持 127.0.0.1 就好。
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
