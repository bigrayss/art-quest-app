"""画到一半时的陪伴。system 是 v0.3 的 `during` 原文（见 artquest/prompts/），
规矩都在那段里：回应画面里一个具体的东西、最多给一个小思路、不评分不挑错。
"""
from typing import Any, Dict

from ..config import LLM_BACKEND
from ..feedback.claude_feedback import output_lines, task_lines
from ..llm import claude_text, image_block
from ..prompts import lang_of, system


class ClaudeAssist:
    backend = LLM_BACKEND   # claude / ecnu / …，跟环境变量里配的提供方走

    def assist(self, image_png: bytes, quest: Dict[str, Any], intent: Dict[str, Any],
               nth: int = 1) -> Dict[str, Any]:
        lang = lang_of(quest)
        nth_line = (f"This is the learner's request number {nth} during this drawing."
                    if lang == "en" else f"这是学生这次画画中第 {nth} 次点开你。")
        lines = task_lines(quest, intent, lang) + [nth_line, ""] + output_lines(
            quest, lang, "简单版：只说一句，不超过 15 字。", "Simple version: one sentence, at most 10 words.")
        content = [{"type": "text", "text": "Current artwork (in progress):" if lang == "en" else "当前作品（还在画）："},
                   image_block(image_png),
                   {"type": "text", "text": "\n".join(lines)}]
        text = claude_text(system(lang, "during"), content, max_tokens=200)
        return {"text": text.strip(), "backend": self.backend}
