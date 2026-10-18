#!/usr/bin/env python3
"""探测模型后端支不支持工具协议（agent 选题臂要用）。只打印结果，不打印 key。

在服务器上跑（key 在那边的环境变量里；先把环境变量文件 source 进来再跑）：
    cd ~/artquest && .venv/bin/python tools/probe_tools.py

四个探测：
  A  带 tools 参数、tool_choice=auto，问一个必须查工具才能答的问题 → 看回不回 tool_calls
  B  tool_choice 强制指定那个工具 → 看网关认不认这个参数
  C  不带 tools，只在 system 里写工具说明、要求回一个 JSON → 看模拟协议走不走得通
  D  同 C，但看模型会不会自己吐 Qwen 风格的 <tool_call> 标签
最后给结论：native（原生可用）/ emulated（要我们自己模拟）/ blocked（都不行）。
"""
import json
import os
import re
import sys
import time

try:
    import httpx
except ImportError:
    sys.exit("需要 httpx（.venv 里有）")

BASE = os.environ.get("ARTQUEST_LLM_BASE_URL", "").rstrip("/")
KEYS = [k.strip() for k in os.environ.get("ARTQUEST_LLM_API_KEY", "").split(",") if k.strip()]
MODEL = os.environ.get("ARTQUEST_MODEL", "ecnu-plus")
TIMEOUT = float(os.environ.get("ARTQUEST_LLM_TIMEOUT", "60"))
if not BASE or not KEYS:
    sys.exit("环境里没有 ARTQUEST_LLM_BASE_URL / ARTQUEST_LLM_API_KEY（先把环境变量文件 source 进来）")
KEY = KEYS[0]

TOOL = {"type": "function", "function": {
    "name": "lookup_record",
    "description": "按编号查一条记录，返回它的内容。",
    "parameters": {"type": "object", "properties": {"record_id": {"type": "integer"}}, "required": ["record_id"],
                   "additionalProperties": False}}}
QUESTION = "请查一下编号为 42 的记录里写了什么。你没有这条记录的内容，必须用工具查。"


def scrub(text: str) -> str:
    for k in KEYS:
        text = text.replace(k, "<key>")
    return text


def post(body):
    t0 = time.monotonic()
    try:
        r = httpx.post(f"{BASE}/chat/completions", json=body, timeout=TIMEOUT,
                       headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    except Exception as e:
        return None, f"{type(e).__name__}: {e}", time.monotonic() - t0
    return r, None, time.monotonic() - t0


def show(name, r, err, dt):
    print(f"\n== {name} ==  {dt:.1f}s")
    if err:
        print("  请求失败：", scrub(err)[:300]); return None
    print("  HTTP", r.status_code)
    if r.status_code >= 400:
        print("  错误体：", scrub(r.text)[:400]); return None
    try:
        data = r.json()
    except Exception:
        print("  不是 JSON：", scrub(r.text)[:300]); return None
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    calls = msg.get("tool_calls") or []
    content = msg.get("content") or ""
    print("  finish_reason:", choice.get("finish_reason"))
    print("  tool_calls:", json.dumps([{"name": (c.get("function") or {}).get("name"),
                                        "arguments": (c.get("function") or {}).get("arguments")} for c in calls],
                                      ensure_ascii=False) if calls else "（没有）")
    print("  content:", scrub(str(content))[:240].replace("\n", " "))
    if msg.get("reasoning_content"):
        print("  reasoning_content:", len(msg["reasoning_content"]), "字（被忽略）")
    return {"calls": calls, "content": str(content), "finish": choice.get("finish_reason")}


def base_body():
    return {"model": MODEL, "max_tokens": 300, "stream": False, "thinking": {"type": "disabled"}}


results = {}
b = base_body(); b["messages"] = [{"role": "user", "content": QUESTION}]; b["tools"] = [TOOL]; b["tool_choice"] = "auto"
results["A"] = show("A 原生 tools + tool_choice=auto", *post(b))
b = base_body(); b["messages"] = [{"role": "user", "content": QUESTION}]; b["tools"] = [TOOL]
b["tool_choice"] = {"type": "function", "function": {"name": "lookup_record"}}
results["B"] = show("B 原生 tools + 强制 tool_choice", *post(b))
sys_c = ("你可以使用一个工具：lookup_record(record_id: int)，按编号查记录。\n"
         "需要用工具时，只输出一个 JSON 对象：{\"tool\": \"lookup_record\", \"arguments\": {\"record_id\": 42}}，不要别的文字。\n"
         "不需要工具时输出 {\"final\": \"你的回答\"}。")
b = base_body(); b["messages"] = [{"role": "system", "content": sys_c}, {"role": "user", "content": QUESTION}]
results["C"] = show("C 模拟协议（system 说明 + 只回 JSON）", *post(b))
sys_d = ("# Tools\nYou may call the following function. Return a call as\n<tool_call>\n{\"name\": \"lookup_record\", \"arguments\": {\"record_id\": 42}}\n</tool_call>\n"
         + json.dumps(TOOL["function"], ensure_ascii=False))
b = base_body(); b["messages"] = [{"role": "system", "content": sys_d}, {"role": "user", "content": QUESTION}]
results["D"] = show("D 模拟协议（Qwen 风格 <tool_call> 标签）", *post(b))

print("\n== 结论 ==")
a, c, d = results.get("A"), results.get("C"), results.get("D")
native = bool(a and a["calls"] and any((x.get("function") or {}).get("name") == "lookup_record" for x in a["calls"]))
emul_json = False
if c:
    m = re.search(r"\{.*\}", c["content"], flags=re.S)
    try:
        obj = json.loads(m.group(0)) if m else None
        emul_json = bool(obj and obj.get("tool") == "lookup_record" and (obj.get("arguments") or {}).get("record_id") == 42)
    except Exception:
        emul_json = False
emul_tag = bool(d and "<tool_call>" in d["content"] and "lookup_record" in d["content"])
if native:
    print("native：网关放行 tools，模型回 tool_calls → ARTQUEST_LLM_TOOLS=native 即可，不用写模拟。")
elif emul_json or emul_tag:
    print(f"emulated：原生不通，但模拟协议可行（JSON={emul_json}，<tool_call> 标签={emul_tag}）→ 要写模拟分支，ARTQUEST_LLM_TOOLS=emulated。")
else:
    print("blocked：原生和模拟都没拿到一次像样的工具调用；看上面各项的 HTTP 状态和内容再定。")
