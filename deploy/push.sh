#!/usr/bin/env bash
# 在本机执行：把代码推上服务器并重启服务。
#
#   ./deploy/push.sh              # 用 ~/.ssh/config 里的 Host artquest
#   ./deploy/push.sh ray@1.2.3.4  # 或直接给地址
#
# 这台机器上**没有 sudo**，所以整套东西都装在家目录里：代码 ~/artquest，
# 服务走 systemd --user，对这台机器零侵入。
#
# 第一次会自动 bootstrap（查 python/venv、开 linger、建目录）。
# 之后每次改完代码重跑同一条命令即可。
# data/ 和 .env 只在服务器上，本机的绝不会覆盖它们。
set -euo pipefail
cd "$(dirname "$0")/.."

TARGET="${1:-${ARTQUEST_SSH:-artquest}}"
APP_DIR='$HOME/artquest'      # 单引号：留到远端再展开
PORT=8010

echo "==> 目标：$TARGET"
ssh "$TARGET" 'bash -s' < deploy/bootstrap.sh

echo "==> 同步代码（跳过 data/.env/.venv/.git）"
rsync -az --delete \
  --exclude 'data/' --exclude '.env' --exclude '.venv/' --exclude '.git/' \
  --exclude '__pycache__/' --exclude '*.pyc' --exclude '.pytest_cache/' \
  --exclude 'tools/fonts-src/' --exclude 'ios/' --exclude '.github/' --exclude 'docs/*.pdf' --exclude 'docs/*.docx' \
  -e "ssh" ./ "$TARGET:artquest/"

echo "==> 建/更新 venv、装依赖、装服务、重启"
ssh "$TARGET" "bash -s" <<'REMOTE'
set -euo pipefail
cd "$HOME/artquest"
export PATH="$HOME/.local/bin:$PATH"
PIP_INDEX="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
# 这台机器缺 ensurepip（装它要 sudo），所以标准 venv 建不出来，退到 virtualenv。
# 两条路建出来的 .venv 结构一样，后面的命令不用分叉。
if [ ! -d .venv ]; then
  if python3 -c "import ensurepip" 2>/dev/null; then python3 -m venv .venv; else virtualenv -q .venv; fi
fi
.venv/bin/pip install -q --upgrade -i "$PIP_INDEX" pip
.venv/bin/pip install -q -i "$PIP_INDEX" -r requirements.txt
mkdir -p data
install -m 644 deploy/artquest.service "$HOME/.config/systemd/user/artquest.service"
systemctl --user daemon-reload
systemctl --user enable --now artquest
sleep 2
systemctl --user is-active --quiet artquest && echo "服务在跑" || { systemctl --user status artquest --no-pager -l | tail -20; exit 1; }
curl -fsS -o /dev/null http://127.0.0.1:8010/ && echo "本地自检 200 OK"
REMOTE

cat <<EOF

==> 好了。服务绑的是 127.0.0.1:$PORT，没有对公网开放。

**正式入口**是 https://art.ddhulu.cn/ ——需要对方加好 A 记录并往
/etc/caddy/Caddyfile 追加 deploy/Caddyfile.artquest 那一段（见指南第二封信）。

Caddy 还没接上之前，自己调试开一条隧道（占着终端，Ctrl-C 结束）：

    ssh -N -L $PORT:127.0.0.1:$PORT $TARGET

然后浏览器开  http://127.0.0.1:$PORT/

看日志：   ssh $TARGET journalctl --user -u artquest -f
重启：     ssh $TARGET systemctl --user restart artquest
停掉：     ssh $TARGET systemctl --user disable --now artquest
EOF
