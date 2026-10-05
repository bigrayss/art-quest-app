"""交卷后的话，两段 system 都来自 v0.3 提示词文件：

* feedback()  第一次交卷，还能改一次 → `review`
* compare()   改完再交 → `final`，带着修改前的图（只有给了可比的前图，才能提「变化」）

system 原样用，不拼通用提示（usage 这么要求）。任务、想法、心情、九维分数都放进 user 消息；
分数只给数字——量规说明是打分时的事。图前面带一行标签（「当前作品：」），让模型知道哪张是哪张。
"""
from typing import Any, Dict, List

from ..config import LLM_BACKEND
from ..llm import claude_text, image_block
from ..prompts import DIM_NAMES, lang_of, system
from ..scoring.base import DIM_KEYS
from .template_feedback import emotion_en


def task_lines(quest: Dict[str, Any], intent: Dict[str, Any], lang: str) -> List[str]:
    mood = (intent.get("emotion") or "").strip()
    idea = (intent.get("text") or "").strip()
    if lang == "en":
        return [f"Task: {quest.get('title', '')}",
                f"Task requirements: {quest.get('prompt', '')}",
                f"What the learner said they want to draw: {idea or '(nothing written)'}",
                f"How the learner felt before starting: {emotion_en(mood) if mood else '(not chosen)'}"]
    return [f"绘画任务：{quest.get('title', '')}",
            f"任务要求：{quest.get('prompt', '')}",
            f"学生写下的想法：{idea or '（没写）'}",
            f"学生画前的心情：{mood or '（没选）'}"]


def score_lines(scores: Dict[str, Any], lang: str) -> List[str]:
    """九维分数，一行一维。考不到的维度写明，不给数字；一个分都没有就说没有。"""
    dims = (scores or {}).get("dims") or {}
    names = DIM_NAMES[lang]
    rows = []
    for k in DIM_KEYS:
        e = dims.get(k) or {}
        if e.get("score") is not None:
            rows.append(f"- {names[k]}: {e['score']}" if lang == "en" else f"- {names[k]}：{e['score']}")
        elif e.get("na"):
            rows.append(f"- {names[k]}: not assessed for this task" if lang == "en" else f"- {names[k]}：本任务不考察")
    if not rows:
        return ["Nine-dimensional scores: not available." if lang == "en" else "九维评分：未提供。"]
    return (["Nine-dimensional scores (1-5):"] if lang == "en" else ["九维评分（1–5）："]) + rows


def output_lines(quest: Dict[str, Any], lang: str, simple_zh: str, simple_en: str) -> List[str]:
    out = ["Output language: English." if lang == "en" else "输出语言：简体中文。"]
    if quest.get("ui") == "simple":
        out.append(simple_en if lang == "en" else simple_zh)
    return out


class ClaudeFeedback:
    name = LLM_BACKEND   # claude / ecnu / …，跟环境变量里配的提供方走

    def feedback(self, image_png: bytes, quest: Dict[str, Any], intent: Dict[str, Any], scores: Dict[str, Any]) -> Dict[str, Any]:
        lang = lang_of(quest)
        lines = task_lines(quest, intent, lang) + [""] + score_lines(scores, lang) + [""] + output_lines(
            quest, lang, "简单版：只写一句话，不超过 20 字。", "Simple version: one sentence, at most 12 words.")
        content = [{"type": "text", "text": "Current artwork:" if lang == "en" else "当前作品："},
                   image_block(image_png),
                   {"type": "text", "text": "\n".join(lines)}]
        text = claude_text(system(lang, "review"), content, max_tokens=600)
        return {"backend": self.name, "text": text}

    def compare(self, before_png: bytes, after_png: bytes, before_scores: Dict[str, Any], after_scores: Dict[str, Any],
                quest: Dict[str, Any], intent: Dict[str, Any]) -> Dict[str, Any]:
        lang = lang_of(quest)
        lines = task_lines(quest, intent, lang) + [""] + output_lines(
            quest, lang, "简单版：只写一句话，不超过 25 字。", "Simple version: one sentence, at most 20 words.")
        content = [{"type": "text", "text": "Pre-revision artwork:" if lang == "en" else "修改前的作品："},
                   image_block(before_png),
                   {"type": "text", "text": "Final artwork:" if lang == "en" else "最终作品："},
                   image_block(after_png),
                   {"type": "text", "text": "\n".join(lines)}]
        text = claude_text(system(lang, "final"), content, max_tokens=500)
        return {"backend": self.name, "text": text}
