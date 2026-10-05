#!/usr/bin/env python3
"""探网关的并发闸是按 key 开还是按模型开。配好环境变量（多个 key 逗号分隔）后在服务器上跑：

    set -a; . ./.env; set +a; .venv/bin/python tools/probe_concurrency.py [N]

做法：绕开程序里的排队，直接同时发 N 个最小的文字请求（默认 10），分三轮：
  1. 只用第 1 把 key      → 超过 5 路就该 429
  2. 只用第 2 把 key      → 同上（证明每把 key 各有各的闸）
  3. 所有 key 轮着用      → 如果闸按 key 开，N ≤ 5×key 数就该全 200；按模型开则还是只有 5 个 200
只打印状态码和耗时，不打印 key。不写任何数据。
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx  # noqa: E402

from artquest import config  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
KEYS = config.LLM_API_KEYS
if not KEYS:
    sys.exit("没有 key")


def one(key):
    t = time.time()
    try:
        r = httpx.post(f"{config.LLM_BASE_URL}/chat/completions", timeout=60,
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": config.LLM_MODEL, "max_tokens": 4, "thinking": {"type": "disabled"},
                             "messages": [{"role": "user", "content": "回「通」。"}]})
        return r.status_code, round(time.time() - t, 1)
    except Exception as e:
        return type(e).__name__, round(time.time() - t, 1)


def burst(label, keys):
    with ThreadPoolExecutor(max_workers=N) as ex:
        res = list(ex.map(one, [keys[i % len(keys)] for i in range(N)]))
    ok = sum(1 for c, _ in res if c == 200)
    busy = sum(1 for c, _ in res if c == 429)
    print(f"{label:28s} 同时 {N} 个 → 200 ×{ok}  429 ×{busy}  其他 ×{N - ok - busy}  耗时 {[t for _, t in res]}")


print(f"keys={len(KEYS)} model={config.LLM_MODEL}")
burst("第 1 把 key", KEYS[:1])
time.sleep(3)
if len(KEYS) > 1:
    burst("第 2 把 key", KEYS[1:2])
    time.sleep(3)
    burst(f"全部 {len(KEYS)} 把轮着用", KEYS)
    print("\n判断：第三轮的 200 数明显多于前两轮 → 闸按 key 开，多给 key 有用；和前两轮差不多 → 闸按模型开，只能找平台提额。")
else:
    print("\n只有一把 key，等第二把加进来再跑一次。")
