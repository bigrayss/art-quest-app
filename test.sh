#!/usr/bin/env bash
# 基础功能测试（离线：heuristic 评分 + template 反馈，不需要 API key，不需要画画）
# 用法: ./test.sh
set -euo pipefail
cd "$(dirname "$0")"

# 首次运行自动建虚拟环境并装依赖
if [ ! -d .venv ]; then
  echo "== 首次运行：创建 .venv 并安装依赖 =="
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

echo "== 运行基础功能测试 =="
.venv/bin/python -m unittest -v
