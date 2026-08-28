"""Thin wrapper around the Anthropic SDK used by the Claude scorer and feedback engine.

Model: Claude Opus 5 (configurable via ARTQUEST_MODEL). Thinking is adaptive by
default on Opus 5, so we only set effort. Server-side refusal fallbacks are
enabled ("default" mode) so a safety refusal is re-routed instead of failing.
"""
import base64
import json
from typing import Any, Dict, List

from .config import CLAUDE_EFFORT, CLAUDE_MODEL

_client = None


def client():
    global _client
    if _client is None:
        import anthropic  # imported lazily so the app runs without the SDK configured
        _client = anthropic.Anthropic()
    return _client


def image_block(png: bytes, media_type: str = "image/png") -> Dict[str, Any]:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": base64.standard_b64encode(png).decode("ascii")},
    }


class ClaudeRefused(RuntimeError):
    pass


def _create(system: str, content: List[Dict[str, Any]], max_tokens: int, **extra: Any):
    resp = client().beta.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        **extra,
    )
    if resp.stop_reason == "refusal":
        detail = getattr(resp, "stop_details", None)
        raise ClaudeRefused(f"model declined the request: {detail}")
    return resp


def claude_text(system: str, content: List[Dict[str, Any]], max_tokens: int = 2048) -> str:
    resp = _create(system, content, max_tokens, output_config={"effort": CLAUDE_EFFORT})
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def claude_json(system: str, content: List[Dict[str, Any]], schema: Dict[str, Any], max_tokens: int = 4096) -> Dict[str, Any]:
    resp = _create(
        system,
        content,
        max_tokens,
        output_config={"effort": CLAUDE_EFFORT, "format": {"type": "json_schema", "schema": schema}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)
