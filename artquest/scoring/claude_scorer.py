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
SCHEMA = {
    "type": "object",
    "properties": {
        "dims": {
            "type": "object",
            "properties": {k: _dim_schema for k in DIM_KEYS},
            "required": DIM_KEYS,
            "additionalProperties": False,
        },
        "summary": {"type": "string"},
    },
    "required": ["dims", "summary"],
    "additionalProperties": False,
}


class ClaudeScorer:
    name = "claude"

    def score(self, image_png: bytes, quest: Dict[str, Any], intent: Dict[str, Any]) -> Dict[str, Any]:
        prompt = (
            f"任务：{quest['title']}\n任务说明：{quest['prompt']}\n"
            f"本任务重点维度：{', '.join(quest.get('focus_dims', []))}\n"
            f"作者画前情绪：{intent.get('emotion', '')}\n作者创作意图：{intent.get('text', '') or '（未填写）'}\n\n"
            "请对这幅作品进行九维评分，并用一两句话总结（summary，中文，≤60 字）。"
        )
        data = claude_json(SYSTEM, [image_block(image_png), {"type": "text", "text": prompt}], SCHEMA)
        res = empty_result(self.name)
        for k in DIM_KEYS:
            d = data["dims"][k]
            res["dims"][k] = {"score": round(max(1.0, min(float(SCALE_MAX), float(d["score"]))), 1), "note": d["note"]}
        res["summary"] = data["summary"]
        return res
