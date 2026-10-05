"""模型调用的薄封装。评分 / 反馈 / 陪伴 / 个性化四处都只经过这里。

两条通路，调用方看不出差别（同样的 system + Anthropic 风格的 content 块 + 可选 JSON schema）：

* anthropic  Anthropic SDK。Opus 5 的 thinking 自适应，只设 effort；开了服务端 refusal 回退。
* openai     任何 OpenAI 兼容的 /chat/completions（现在接的是华东师大 ecnu-plus，底是 Qwen3 系列
             的 27B，支持图片，但**没有 json_schema / response_format**，所以结构化输出靠提示词
             + 解析 + 校验）。走 httpx，不另装 SDK。

函数名还叫 claude_*，因为四个引擎都这么引；它们的意思是「问模型」。
"""
import base64
import json
import logging
import os
import re
import time
from typing import Any, Dict, List

from .config import (LLM_API_KEY, LLM_BASE_URL, LLM_EFFORT, LLM_EXTRA, LLM_MODEL, LLM_PROVIDER,
                     LLM_THINKING, LLM_TIMEOUT_SEC)

log = logging.getLogger("artquest")
_client = None
# 华东师大的网关每个模型最多 5 个并发（429 model_concurrency_exceeded），整个账号共用。
# 进程内先用一道闸把并发压到 4（留一个给别人），撞上 429 再退避重试。
import threading
_GATE = threading.BoundedSemaphore(int(os.environ.get("ARTQUEST_LLM_CONCURRENCY", "4")))
_RETRY_SLEEP = (1.0, 2.5, 5.0)
# 最近一次 openai 通路调用的体检单（耗时、token、有没有思维链），tools/try_llm.py 打印它。
LAST_CALL: Dict[str, Any] = {}


class ClaudeRefused(RuntimeError):
    pass


class LLMBadOutput(RuntimeError):
    """模型答了，但不是要的形状（比如要 JSON 给了散文）。"""


def image_block(png: bytes, media_type: str = "image/png") -> Dict[str, Any]:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": base64.standard_b64encode(png).decode("ascii")},
    }


# ---- anthropic ------------------------------------------------------------------

def client():
    global _client
    if _client is None:
        import anthropic  # imported lazily so the app runs without the SDK configured
        _client = anthropic.Anthropic()
    return _client


def _anthropic_create(system: str, content: List[Dict[str, Any]], max_tokens: int, **extra: Any):
    resp = client().beta.messages.create(
        model=LLM_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": content}],
        **({"system": system} if system else {}),
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        **extra,
    )
    if resp.stop_reason == "refusal":
        detail = getattr(resp, "stop_details", None)
        raise ClaudeRefused(f"model declined the request: {detail}")
    return resp


def _anthropic_text(system: str, content: List[Dict[str, Any]], max_tokens: int) -> str:
    resp = _anthropic_create(system, content, max_tokens, output_config={"effort": LLM_EFFORT})
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _anthropic_json(system: str, content: List[Dict[str, Any]], schema: Dict[str, Any], max_tokens: int) -> Dict[str, Any]:
    resp = _anthropic_create(
        system, content, max_tokens,
        output_config={"effort": LLM_EFFORT, "format": {"type": "json_schema", "schema": schema}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


# ---- openai 兼容 -------------------------------------------------------------------

def to_openai_content(content: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Anthropic 风格的块 → OpenAI 风格。图片走 data URL（ecnu 文档明确收这个）。"""
    out = []
    for b in content:
        if b["type"] == "text":
            out.append({"type": "text", "text": b["text"]})
        elif b["type"] == "image":
            src = b["source"]
            out.append({"type": "image_url",
                        "image_url": {"url": f"data:{src['media_type']};base64,{src['data']}"}})
        else:
            raise ValueError(f"unsupported content block: {b['type']}")
    return out


def openai_request(system: str, content: List[Dict[str, Any]], max_tokens: int) -> Dict[str, Any]:
    messages = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": to_openai_content(content)}]
    body: Dict[str, Any] = {
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
    }
    # ecnu 的开关：{"type": "enabled"|"disabled"}。关着时不送 reasoning_effort，
    # 别的 OpenAI 兼容服务不认这两个字段也最多忽略。
    body["thinking"] = {"type": "enabled" if LLM_THINKING else "disabled"}
    if LLM_THINKING:
        body["reasoning_effort"] = LLM_EFFORT
    body.update(LLM_EXTRA)      # 试参数用的后门（ARTQUEST_LLM_EXTRA 是一段 JSON），不改代码就能加字段
    return body


def _openai_post(body: Dict[str, Any]) -> Dict[str, Any]:
    import httpx
    for attempt in range(len(_RETRY_SLEEP) + 1):
        t0 = time.monotonic()
        with _GATE:
            r = httpx.post(f"{LLM_BASE_URL}/chat/completions", json=body, timeout=LLM_TIMEOUT_SEC,
                           headers={"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"})
        dt = time.monotonic() - t0
        if r.status_code in (429, 502, 503, 504) and attempt < len(_RETRY_SLEEP):
            log.warning("llm %s %.1fs HTTP %d, retry in %.1fs", body.get("model"), dt, r.status_code, _RETRY_SLEEP[attempt])
            time.sleep(_RETRY_SLEEP[attempt])
            continue
        if r.status_code >= 400:
            log.warning("llm %s %.1fs HTTP %d", body.get("model"), dt, r.status_code)
            raise RuntimeError(f"{LLM_PROVIDER} {r.status_code}: {r.text[:300]}")
        data = r.json()
        _record_call(body, data, dt)
        return data
    raise RuntimeError("unreachable")


def _record_call(body: Dict[str, Any], data: Dict[str, Any], dt: float) -> None:
    """只记长度和计数，不记内容：日志里不能有孩子的画和话。"""
    usage = data.get("usage") or {}
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    has_image = any(isinstance(m.get("content"), list) and any(p.get("type") == "image_url" for p in m["content"])
                    for m in body.get("messages", []))
    LAST_CALL.clear()
    LAST_CALL.update(seconds=round(dt, 1), model=body.get("model"), image=has_image,
                     thinking_requested=body.get("thinking"), prompt_tokens=usage.get("prompt_tokens"),
                     completion_tokens=usage.get("completion_tokens"), finish_reason=choice.get("finish_reason"),
                     content_chars=len(content) if isinstance(content, str) else -1,
                     reasoning_chars=len(reasoning) if isinstance(reasoning, str) else -1)
    log.info("llm call %s", json.dumps(LAST_CALL, ensure_ascii=False))
    if reasoning and not LLM_THINKING:
        log.warning("llm: thinking was requested off but the reply carries %d chars of reasoning_content", len(reasoning))


def openai_reply_text(data: Dict[str, Any]) -> str:
    """只取 content，不取 reasoning_content（思维链不是给孩子看的）。"""
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        raise LLMBadOutput(f"unexpected response shape: {json.dumps(data)[:300]}")
    text = msg.get("content") or ""
    if isinstance(text, list):   # 少数兼容实现把 content 回成块列表
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    # 有的实现在关 thinking 之后仍把 <think>…</think> 混进 content
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return text.strip()


def _openai_text(system: str, content: List[Dict[str, Any]], max_tokens: int) -> str:
    return openai_reply_text(_openai_post(openai_request(system, content, max_tokens)))


_JSON_NOTE = ("\n\n只输出一个 JSON 对象，不要 Markdown 代码块，不要任何解释文字。"
              "它必须符合这个 JSON Schema：\n")


def parse_json_reply(text: str) -> Dict[str, Any]:
    """宽一点地取 JSON：剥代码块、取第一个 { 到最后一个 }。"""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        raise LLMBadOutput(f"no JSON object in reply: {text[:200]!r}")
    try:
        obj = json.loads(t[start:end + 1])
    except json.JSONDecodeError as e:
        raise LLMBadOutput(f"malformed JSON in reply: {e}: {text[:200]!r}")
    if not isinstance(obj, dict):
        raise LLMBadOutput("reply is JSON but not an object")
    return obj


def check_schema(obj: Any, schema: Dict[str, Any], path: str = "$") -> None:
    """够用的子集校验：type / required / properties / items / additionalProperties。
    评分的 schema 只用到这些；缺一个维度就报错，不让半份分数混进记录。"""
    t = schema.get("type")
    if t == "object":
        if not isinstance(obj, dict):
            raise LLMBadOutput(f"{path}: expected object")
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in obj:
                raise LLMBadOutput(f"{path}.{k}: missing")
        if schema.get("additionalProperties") is False:
            for k in list(obj):
                if k not in props:
                    del obj[k]          # 多给的字段丢掉，不算错
        for k, sub in props.items():
            if k in obj:
                check_schema(obj[k], sub, f"{path}.{k}")
    elif t == "array":
        if not isinstance(obj, list):
            raise LLMBadOutput(f"{path}: expected array")
        if "maxItems" in schema and len(obj) > schema["maxItems"]:
            del obj[schema["maxItems"]:]
        for i, it in enumerate(obj):
            check_schema(it, schema.get("items", {}), f"{path}[{i}]")
    elif t == "number":
        if isinstance(obj, bool) or not isinstance(obj, (int, float)):
            raise LLMBadOutput(f"{path}: expected number, got {obj!r}")
    elif t == "integer":
        if isinstance(obj, bool) or not isinstance(obj, int):
            raise LLMBadOutput(f"{path}: expected integer, got {obj!r}")
    elif t == "string":
        if not isinstance(obj, str):
            raise LLMBadOutput(f"{path}: expected string, got {obj!r}")
    elif t == "boolean":
        if not isinstance(obj, bool):
            raise LLMBadOutput(f"{path}: expected boolean, got {obj!r}")


def _openai_json(system: str, content: List[Dict[str, Any]], schema: Dict[str, Any], max_tokens: int) -> Dict[str, Any]:
    sys_full = system + _JSON_NOTE + json.dumps(schema, ensure_ascii=False)
    body = openai_request(sys_full, content, max_tokens)
    last: Exception = LLMBadOutput("no attempt")
    for attempt in range(2):          # 形状不对就再要一次；第二次还不对才放弃
        try:
            obj = parse_json_reply(openai_reply_text(_openai_post(body)))
            check_schema(obj, schema)
            return obj
        except LLMBadOutput as e:
            last = e
            log.warning("llm json attempt %d rejected: %s", attempt + 1, e)
    raise last


# ---- 对外 ----------------------------------------------------------------------------

def claude_text(system: str, content: List[Dict[str, Any]], max_tokens: int = 2048) -> str:
    if LLM_PROVIDER == "openai":
        return _openai_text(system, content, max_tokens)
    return _anthropic_text(system, content, max_tokens)


def claude_json(system: str, content: List[Dict[str, Any]], schema: Dict[str, Any], max_tokens: int = 4096) -> Dict[str, Any]:
    if LLM_PROVIDER == "openai":
        return _openai_json(system, content, schema, max_tokens)
    return _anthropic_json(system, content, schema, max_tokens)


llm_text, llm_json = claude_text, claude_json
