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
from typing import Any, Dict, List, Optional

from .config import (LLM_API_KEY, LLM_API_KEYS, LLM_BACKEND, LLM_BASE_URL, LLM_EFFORT, LLM_EXTRA, LLM_MODEL, LLM_PROVIDER,
                     LLM_THINKING, LLM_TIMEOUT_SEC)

log = logging.getLogger("artquest")
_client = None
# 华东师大的网关每个 key 最多 5 个并发（429 model_concurrency_exceeded）。
# 进程内每个 key 一条队、每队最多 4 路在飞（留一路给别人）；多个 key 时每次挑最空的那条。
# 撞上 429 退避后重试，重试时重新挑 key。key 本身绝不进日志，只记编号。
import threading
_PER_KEY = int(os.environ.get("ARTQUEST_LLM_CONCURRENCY", "4"))
_RETRY_SLEEP = (1.0, 2.5, 5.0)


class _KeyPool:
    """几把 key 几条队。`acquire()` 挑在飞最少的那把，都满了就等；`release()` 还回去并叫醒等的人。"""

    def __init__(self, keys, per_key):
        self.keys = list(keys) or [""]
        self.per_key = max(1, per_key)
        self.inflight = [0] * len(self.keys)
        self.cooling = [0.0] * len(self.keys)      # 刚撞过 429 的 key 歇到什么时候（monotonic）
        self.cv = threading.Condition()

    def acquire(self, avoid: Optional[int] = None) -> int:
        """挑一把：先排除正在冷却的和刚撞墙的（avoid），剩下的里挑在飞最少的；都满了就等。
        只有一把 key 时没得挑，只能等它空出来。"""
        with self.cv:
            while True:
                now = time.monotonic()
                cands = [j for j in range(len(self.keys)) if self.cooling[j] <= now and j != avoid]
                if not cands:
                    cands = list(range(len(self.keys)))
                i = min(cands, key=lambda j: self.inflight[j])
                if self.inflight[i] < self.per_key:
                    self.inflight[i] += 1
                    return i
                self.cv.wait(timeout=0.5)

    def release(self, i: int, cool: float = 0.0) -> None:
        with self.cv:
            self.inflight[i] -= 1
            if cool > 0:
                self.cooling[i] = time.monotonic() + cool
            self.cv.notify()

    def snapshot(self):
        with self.cv:
            return list(self.inflight)


_POOL = _KeyPool(LLM_API_KEYS, _PER_KEY)
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


# ---- 调用记录（2026-10-14）-------------------------------------------------------------
#
# 三层：group（一轮业务执行，比如第一次九维评分）> operation（组里的一个逻辑操作，比如「评构图」）
# > call（一次真实执行；429 重试、JSON 形状不对再要一次，各算一次 attempt）。
# 每次 attempt **结束时写一条**完整记录（成功 / HTTP 错 / 异常 / 形状不对），不做 start/end 双行；
# 进程硬崩可能漏记，所以这份日志不宣称覆盖所有 HTTP 尝试。
# 落盘由 sink 负责（storage.add_call → session 目录里的 calls.jsonl）：完整输入输出只进 session 的隐私边界，
# 上面的 `_record_call` 继续只记统计。固定的 system 正文不重复存，只记 hash，正文由 sink 按 hash 归档一份。
# 没有 recording 上下文时（tools/try_llm.py 这类）什么都不多记。
import contextvars
import hashlib
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

_CTX: "contextvars.ContextVar[Optional[CallContext]]" = contextvars.ContextVar("artquest_llm_ctx", default=None)
PURPOSES = ("score", "review", "final", "assist", "personalize", "select")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CallContext:
    """一个 operation 的记录簿：把每次 attempt 拼成一条、结果定性后交给 sink。

    `images` 是 sha256 → 文件相对路径：调用方刚把图存到哪，记录里就能指回去（图本身不进记录）。
    `adopted` 是 fork 出去的子操作汇报上来的「被采用的那次」（dimension_id → call_id）。
    """

    def __init__(self, sink, *, purpose: str, stage: str = "", group_id: Optional[str] = None,
                 operation_id: Optional[str] = None, dimension_id: str = "", prompt_version: str = "",
                 images: Optional[Dict[str, str]] = None, parent: "Optional[CallContext]" = None,
                 validator=None):
        self.sink = sink
        # 引擎层的「答了但不是要的东西」（比如评分没回数字）：文本层看不出来，所以由引擎给一个
        # validator(text) -> 错误说明或 None，settle("ok") 前过一遍，不合格就记 bad_output。
        self.validator = validator
        self.purpose, self.stage, self.dimension_id = purpose, stage, dimension_id
        self.prompt_version = prompt_version
        self.group_id = group_id or _new_id("grp")
        self.operation_id = operation_id or _new_id("op")
        self.images: Dict[str, str] = dict(images or {})
        self.parent = parent
        self.attempt = 0
        self.count = 0                  # 落盘的记录数（含子操作的）
        self.pending = None             # HTTP 回来了、还没定性的那条 (rec, system)
        self.last_call_id: Optional[str] = None   # 最后一条 outcome=ok 的 call_id = 被采用的那次
        self.adopted: Dict[str, str] = {}
        self._lock = threading.Lock()

    # -- 远程 --
    def _describe(self, content: List[Dict[str, Any]], max_tokens: int) -> Dict[str, Any]:
        texts, images = [], []
        for b in content or []:
            if b.get("type") == "text":
                texts.append(b.get("text", ""))
            elif b.get("type") == "image":
                try:
                    raw = base64.b64decode(b["source"]["data"])
                except Exception:
                    raw = b""
                h = sha256_hex(raw)
                images.append({"sha256": h, "bytes": len(raw), "file": self.images.get(h)})
        return {"text": texts, "images": images, "max_tokens": max_tokens}

    def begin(self, *, system: str, content: List[Dict[str, Any]], max_tokens: int, provider: str,
              model: Optional[str], backend: str, **extra: Any):
        self.attempt += 1
        rec = {"call_id": _new_id("call"), "group_id": self.group_id, "operation_id": self.operation_id,
               "attempt": self.attempt, "purpose": self.purpose, "stage": self.stage,
               "dimension_id": self.dimension_id, "execution_kind": "remote", "provider": provider,
               "backend": backend, "model": model, "prompt_version": self.prompt_version,
               "system_hash": sha256_hex(system.encode("utf-8")) if system else "",
               "started_at": _now_iso(), "input": self._describe(content, max_tokens), **extra}
        return rec, system

    def emit(self, rec: Dict[str, Any], system: Optional[str], *, outcome: str, **fields: Any) -> None:
        rec.update(fields)
        rec["outcome"] = outcome
        rec.setdefault("seconds", 0.0)
        rec.setdefault("http_status", None)
        rec.setdefault("error", None)
        if outcome == "ok":
            self.last_call_id = rec["call_id"]
        self.count += 1
        try:
            self.sink(rec, system)
        except Exception:               # 记录失败不能挡住孩子的流程
            log.exception("call record sink failed")

    def hold(self, rec: Dict[str, Any], system: Optional[str], **fields: Any) -> None:
        """HTTP 回来了，但 ok 还是 bad_output 要等调用方解析完才知道。"""
        rec.update(fields)
        self.pending = (rec, system)

    def settle(self, outcome: str = "ok", **fields: Any) -> None:
        if not self.pending:
            return
        rec, system = self.pending
        self.pending = None
        if outcome == "ok" and self.validator is not None:
            try:
                err = self.validator(((rec.get("output") or {}).get("text")) or "")
            except Exception as e:      # 校验器自己坏了不算模型的错
                err = None
                log.exception("call validator failed: %s", e)
            if err:
                outcome, fields = "bad_output", {**fields, "error": str(err)[:300]}
        self.emit(rec, system, outcome=outcome, **fields)

    # -- 本地（heuristic / template / no_history）--
    def local(self, *, backend: str, input: Dict[str, Any], output: Dict[str, Any], outcome: str = "ok",
              seconds: float = 0.0, error: Optional[str] = None, model: str = "") -> Dict[str, Any]:
        """没走模型的那次执行也写同形的一条：execution_kind=local，不计 HTTP，没有 token 用量。"""
        rec = {"call_id": _new_id("call"), "group_id": self.group_id, "operation_id": self.operation_id,
               "attempt": 1, "purpose": self.purpose, "stage": self.stage, "dimension_id": self.dimension_id,
               "execution_kind": "local", "provider": "", "backend": backend, "model": model,
               "prompt_version": self.prompt_version, "system_hash": "", "started_at": _now_iso(),
               "input": input, "output": output, "usage": None, "seconds": round(seconds, 3)}
        self.emit(rec, None, outcome=outcome, error=error)
        return rec

    def summary(self) -> Dict[str, Any]:
        """挂在业务记录上的那一小块：这轮是哪个 group、采用了哪几次执行、真发了几次。"""
        return {"group_id": self.group_id, "call_id": self.last_call_id,
                "adopted": dict(self.adopted), "n_records": self.count}


def current() -> Optional[CallContext]:
    return _CTX.get()


@contextmanager
def recording(sink, **fields: Any):
    """开一个 group + 它的第一个 operation。离开时没定性的 pending 记成 unsettled。"""
    ctx = CallContext(sink, **fields)
    token = _CTX.set(ctx)
    try:
        yield ctx
    finally:
        if ctx.pending:
            ctx.settle("unsettled")
        _CTX.reset(token)


@contextmanager
def operation(parent: Optional[CallContext] = None, **fields: Any):
    """同一 group 里再开一个 operation。线程池里的工作线程继承不到 ContextVar，
    所以并行评分把 parent 显式传进来；没有 parent（没人在记录）就什么都不做。"""
    parent = parent or _CTX.get()
    if parent is None:
        yield None
        return
    child = CallContext(parent.sink, purpose=parent.purpose, stage=parent.stage, group_id=parent.group_id,
                        prompt_version=parent.prompt_version, images=parent.images, parent=parent, **fields)
    token = _CTX.set(child)
    try:
        yield child
    finally:
        if child.pending:
            child.settle("unsettled")
        with parent._lock:
            parent.count += child.count
            if child.last_call_id:
                parent.adopted[child.dimension_id or child.operation_id] = child.last_call_id
        _CTX.reset(token)


def _settle(outcome: str = "ok", **fields: Any) -> None:
    ctx = _CTX.get()
    if ctx is not None:
        ctx.settle(outcome, **fields)


# ---- anthropic ------------------------------------------------------------------

def client():
    global _client
    if _client is None:
        import anthropic  # imported lazily so the app runs without the SDK configured
        _client = anthropic.Anthropic()
    return _client


def _anthropic_create(system: str, content: List[Dict[str, Any]], max_tokens: int, **extra: Any):
    ctx = _CTX.get()
    rec = sysx = None
    if ctx is not None:
        rec, sysx = ctx.begin(system=system, content=content, max_tokens=max_tokens, provider="anthropic",
                              model=LLM_MODEL, backend=LLM_BACKEND)
    t0 = time.monotonic()
    try:
        resp = client().beta.messages.create(
            model=LLM_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": content}],
            **({"system": system} if system else {}),
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            **extra,
        )
    except Exception as e:                 # SDK 自己的重试在里面，这里看到的是最终失败
        if ctx is not None:
            ctx.emit(rec, sysx, outcome="exception", seconds=round(time.monotonic() - t0, 2),
                     error=f"{type(e).__name__}: {e}"[:300])
        raise
    dt = time.monotonic() - t0
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    usage = getattr(resp, "usage", None)
    if resp.stop_reason == "refusal":
        detail = getattr(resp, "stop_details", None)
        if ctx is not None:
            ctx.emit(rec, sysx, outcome="refused", seconds=round(dt, 2), http_status=200,
                     error=str(detail)[:300], output={"text": text, "finish_reason": "refusal"})
        raise ClaudeRefused(f"model declined the request: {detail}")
    if ctx is not None:
        ctx.hold(rec, sysx, seconds=round(dt, 2), http_status=200,
                 usage={"prompt_tokens": getattr(usage, "input_tokens", None),
                        "completion_tokens": getattr(usage, "output_tokens", None)},
                 output={"text": text, "finish_reason": resp.stop_reason, "reasoning_chars": 0},
                 provider_request_id=getattr(resp, "id", None))
    return resp


def _anthropic_text(system: str, content: List[Dict[str, Any]], max_tokens: int) -> str:
    resp = _anthropic_create(system, content, max_tokens, output_config={"effort": LLM_EFFORT})
    _settle("ok")
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _anthropic_json(system: str, content: List[Dict[str, Any]], schema: Dict[str, Any], max_tokens: int) -> Dict[str, Any]:
    resp = _anthropic_create(
        system, content, max_tokens,
        output_config={"effort": LLM_EFFORT, "format": {"type": "json_schema", "schema": schema}},
    )
    try:
        text = next(b.text for b in resp.content if b.type == "text")
        obj = json.loads(text)
    except (StopIteration, json.JSONDecodeError) as e:
        _settle("bad_output", error=str(e)[:300])
        raise LLMBadOutput(f"not the JSON asked for: {e}")
    _settle("ok")
    return obj


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


def _openai_post(body: Dict[str, Any], system: str = "", content: Optional[List[Dict[str, Any]]] = None,
                 max_tokens: int = 0) -> Dict[str, Any]:
    """发一次请求（含 429/5xx 重试）。`system/content/max_tokens` 只给调用记录用：body 里已经有它们，
    但记录要的是发送前的原样块（图要算 hash），不是翻译后的 data URL。"""
    import httpx
    ctx = _CTX.get()
    last_key = None
    for attempt in range(len(_RETRY_SLEEP) + 1):
        t0 = time.monotonic()
        ki = _POOL.acquire(avoid=last_key)
        rec = sysx = None
        if ctx is not None:
            rec, sysx = ctx.begin(system=system, content=content or [], max_tokens=max_tokens, provider="openai",
                                  model=body.get("model"), backend=LLM_BACKEND, key_index=ki)
        r = None
        try:
            r = httpx.post(f"{LLM_BASE_URL}/chat/completions", json=body, timeout=LLM_TIMEOUT_SEC,
                           headers={"Authorization": f"Bearer {_POOL.keys[ki]}", "Content-Type": "application/json"})
        except Exception as e:                  # 超时、连不上：这一次 attempt 也要留痕
            _POOL.release(ki)
            if ctx is not None:
                ctx.emit(rec, sysx, outcome="exception", seconds=round(time.monotonic() - t0, 2),
                         error=f"{type(e).__name__}: {e}"[:300])
            raise
        # 撞了 429 的 key 歇一会儿（多把 key 时别人顶上；只有一把时等于退避）
        _POOL.release(ki, cool=_RETRY_SLEEP[min(attempt, len(_RETRY_SLEEP) - 1)] if r.status_code == 429 else 0.0)
        dt = time.monotonic() - t0
        if r.status_code in (429, 502, 503, 504) and attempt < len(_RETRY_SLEEP):
            log.warning("llm %s key#%d %.1fs HTTP %d, retry in %.1fs", body.get("model"), ki, dt, r.status_code, _RETRY_SLEEP[attempt])
            if ctx is not None:
                ctx.emit(rec, sysx, outcome="http_error", seconds=round(dt, 2), http_status=r.status_code,
                         error=r.text[:300], retry_in_s=_RETRY_SLEEP[attempt])
            last_key = ki
            if len(_POOL.keys) == 1:
                time.sleep(_RETRY_SLEEP[attempt])   # 没有别的 key 可换，只能等
            continue
        if r.status_code >= 400:
            log.warning("llm %s %.1fs HTTP %d", body.get("model"), dt, r.status_code)
            if ctx is not None:
                ctx.emit(rec, sysx, outcome="http_error", seconds=round(dt, 2), http_status=r.status_code,
                         error=r.text[:300])
            raise RuntimeError(f"{LLM_PROVIDER} {r.status_code}: {r.text[:300]}")
        data = r.json()
        _record_call(body, data, dt)
        if ctx is not None:
            usage = data.get("usage") or {}
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            reasoning = msg.get("reasoning_content") or ""
            try:
                text = openai_reply_text(data)
            except LLMBadOutput:
                text = ""
            headers = getattr(r, "headers", None) or {}
            ctx.hold(rec, sysx, seconds=round(dt, 2), http_status=r.status_code,
                     usage={"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")},
                     output={"text": text, "finish_reason": choice.get("finish_reason"),
                             "reasoning_chars": len(reasoning) if isinstance(reasoning, str) else -1},
                     provider_request_id=data.get("id") or headers.get("x-request-id"))
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
    LAST_CALL.update(seconds=round(dt, 1), model=body.get("model"), image=has_image, keys=len(_POOL.keys),
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
    text = openai_reply_text(_openai_post(openai_request(system, content, max_tokens), system, content, max_tokens))
    _settle("ok")
    return text


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
            obj = parse_json_reply(openai_reply_text(_openai_post(body, sys_full, content, max_tokens)))
            check_schema(obj, schema)
            _settle("ok")
            return obj
        except LLMBadOutput as e:
            last = e
            _settle("bad_output", error=str(e)[:300])
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
