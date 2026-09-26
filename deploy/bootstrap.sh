#!/usr/bin/env bash
# 在服务器上执行（由 push.sh 自动调用）。幂等，重复跑没事。
#
# 这台机器没有 sudo，所以这里**不装任何系统包、不碰任何系统目录**。
set -euo pipefail

APP_DIR="$HOME/artquest"
export PATH="$HOME/.local/bin:$PATH"
# 机器在国内，走官方 PyPI 会慢到超时。换源（想用别的源就先 export 这个变量）
PIP_INDEX="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

echo "==> 检查 python"
command -v python3 >/dev/null || { echo "没有 python3"; exit 1; }
echo "    $(python3 -V)"

# `python3 -m venv --help` **验不出问题**：Debian/Ubuntu 把 ensurepip 拆进了
# python3.10-venv 包，缺了它 --help 照样成功，真去建的时候才报
# 「ensurepip is not available」。所以这里必须直接问 ensurepip。
echo "==> 检查建 venv 的工具"
if python3 -c "import ensurepip" 2>/dev/null; then
  echo "    ensurepip 在，用标准 venv"
else
  echo "    ensurepip 缺失（装它要 sudo）——改用 virtualenv，它自带 pip 引导"
  if ! command -v virtualenv >/dev/null 2>&1; then
    echo "    装 virtualenv 到 ~/.local"
    pip3 install --user -q -i "$PIP_INDEX" virtualenv
  fi
  command -v virtualenv >/dev/null 2>&1 || { echo "virtualenv 装不上，需要管理员执行：apt install python3.10-venv"; exit 1; }
  echo "    $(virtualenv --version 2>&1 | head -1)"
fi

echo "==> 检查用户级 systemd"
if [ "$(loginctl show-user "$(whoami)" -p Linger --value 2>/dev/null)" != "yes" ]; then
  echo "    开启 linger（否则一登出服务就被停掉）"
  loginctl enable-linger "$(whoami)" || { echo "开不了 linger，需要管理员执行：loginctl enable-linger $(whoami)"; exit 1; }
fi
echo "    Linger=yes"

echo "==> 建目录"
mkdir -p "$APP_DIR/data" "$HOME/.config/systemd/user"

echo "==> bootstrap 完成（全程没碰系统目录）"
