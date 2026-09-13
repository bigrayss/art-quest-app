"""Claude-vision implementation of the 9-dimension rubric with structured output."""
from typing import Any, Dict

from ..llm import claude_json, image_block
from .base import DIMENSIONS, DIM_KEYS, SCALE_MAX, empty_result

SYSTEM = f"""你是儿童美术教育研究中的作品评估员，使用 KidsArtBench 九维体系为一幅儿童/青少年创作打分。
评分范围 1–{SCALE_MAX}（整数或 .5）。评分只用于研究与成长分析，不会直接作为“总分”展示给孩子，所以请诚实、有区分度，不要全部给中间值。
每个维度给一句简短、具体、指向画面内容的说明（中文，≤30 字）。
九个维度：
""" + "\n".join(f"- {d['key']}（{d['zh']} / {d['en']}）：{d['desc']}" for d in DIMENSIONS)

_dim_schema = {
    "type": "object",
    "properties": {"score": {"type": "number"}, "note": {"type": "string"}},
    "required": ["score", "note"],
    "additionalProperties": False,
}


def _schema(keys):
    """Only the applicable dimensions are asked for.

    A task that cannot elicit a dimension must not receive a number for it —
    a forced answer would be indistinguishable from a real low score.
    """
    return {
        "type": "object",
        "properties": {
            "dims": {"type": "object",
                     "properties": {k: _dim_schema for k in keys},
                     "required": list(keys), "additionalProperties": False},
            "summary": {"type": "string"},
        },
        "required": ["dims", "summary"],
        "additionalProperties": False,
    }


SCHEMA = _schema(DIM_KEYS)


class ClaudeScorer:
    name = "claude"

    def score(self, image_png: bytes, quest: Dict[str, Any], intent: Dict[str, Any]) -> Dict[str, Any]:
        keys = [k for k in DIM_KEYS if k in (quest.get("applicable_dims") or DIM_KEYS)]
        prompt = (
            f"任务：{quest['title']}\n任务说明：{quest['prompt']}\n"
            f"本任务重点维度：{', '.join(quest.get('focus_dims', []))}\n"
            f"本任务可评维度：{', '.join(keys)}（其余维度本任务无法考察，不要评）\n"
            f"作者画前情绪：{intent.get('emotion', '')}\n作者创作意图：{intent.get('text', '') or '（未填写）'}\n\n"
            "请只对上面「可评维度」评分，并用一两句话总结（summary，中文，≤60 字）。"
        )
        data = claude_json(SYSTEM, [image_block(image_png), {"type": "text", "text": prompt}], _schema(keys))
        res = empty_result(self.name)
        for k in keys:
            d = data["dims"][k]
            res["dims"][k] = {"score": round(max(1.0, min(float(SCALE_MAX), float(d["score"]))), 1), "note": d["note"]}
        res["summary"] = data["summary"]
        return res
