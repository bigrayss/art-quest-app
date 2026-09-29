"""Claude text feedback: observe → ask → suggest a direction (never an answer)."""
from typing import Any, Dict

from ..llm import claude_text, image_block
from ..scoring.base import DIMENSIONS

_ZH = {d["key"]: d["zh"] for d in DIMENSIONS}
_EN = {d["key"]: d["en"] for d in DIMENSIONS}

SYSTEM = """你在陪一个 6–14 岁的孩子看他刚画完的画。像一个耐心的大孩子坐在旁边说话：短句，说事，不评价，不说教。
硬性原则：
1. 帮助思考，不替代创作：不说“应该画成什么样”，不给标准答案，不描述一张“更好的画”。
2. 只说看到的、比较的、问的；建议只给一个方向，不给结果。
3. 不提分数、不排名、不说“好/不好”。
4. 从孩子自己写的意图出发：画里能看出他想画的吗？意图没写就不提。
5. 只说画里真的有的东西。不夸奖，不用“真棒”“很好”这类词。
6. 每句一个意思，一句不超过 15 个字，不用破折号，不用反问。
7. 中文，全文 60–100 字，分三段，固定开头：「我看到：」「一个问题：」「可以试试：」。最后一段只说一个几分钟能做完的小改动。"""

SYSTEM_SIMPLE_NOTE = "\n简单版：只写一句「试试……」，不超过 15 个字，不分段。"

COMPARE_SYSTEM = """你在陪一个 6–14 岁的孩子看他改画前后的两张图。像一个耐心的大孩子说话：短句，不评价，不说教。
用中文写 30–60 字：先说一处你看到的具体变化（不说好坏），再问一句：改完以后更像他想画的了吗？不提分数，不用破折号。"""

COMPARE_SYSTEM_SIMPLE_NOTE = "\n简单版：只说那一处变化，一句话，不超过 25 个字，不提问。"

# 英文会话：同样的六条硬性原则，只换语言和长度。读者可能只有 6 岁，用词要简单。
SYSTEM_EN = """You are sitting next to a child (age 6–14) looking at the drawing they just finished. Talk like a patient older kid: short sentences, say what you see, no judging, no lecturing.
Hard rules:
1. Help them think; never draw for them. Do not say what it "should" look like, give no model answer, describe no "better picture".
2. Only observe, compare and ask. A suggestion gives one direction, never a result.
3. No scores, no ranking, no "good/bad".
4. Start from what the child wrote they wanted to draw. If they wrote nothing, do not mention it.
5. Only talk about things that are really in the picture. No praise, no "great", "nice", "well done".
6. One idea per sentence, at most 12 words a sentence. No dashes, no rhetorical questions.
7. Simple English a 6-year-old can read. 50–80 words in three short paragraphs, each starting exactly with: "I see:", "One question:", "Try this:". The last paragraph names one small change that takes a few minutes."""

SYSTEM_SIMPLE_NOTE_EN = "\nSimple version: one sentence starting with \"Try\", at most 10 words."

COMPARE_SYSTEM_EN = """You are sitting next to a child (age 6–14) looking at their drawing before and after they changed it. Talk like a patient older kid: short sentences, no judging, no lecturing.
Write 25–45 words in simple English: first say one concrete change you see (no good or bad), then ask one question: is it closer to what they wanted to draw? No scores, no dashes."""

COMPARE_SYSTEM_SIMPLE_NOTE_EN = "\nSimple version: only name that one change, one sentence, at most 20 words, no question."


class ClaudeFeedback:
    name = "claude"

    def feedback(self, image_png: bytes, quest: Dict[str, Any], intent: Dict[str, Any], scores: Dict[str, Any]) -> Dict[str, Any]:
        dims = scores.get("dims", {})
        focus = quest.get("focus_dims", [])
        if quest.get("lang") == "en":
            notes = "\n".join(f"- {_EN[k]}: {dims[k]['note']}" for k in focus if k in dims)
            prompt = (
                f"Task: {quest['title']} — {quest['prompt']}\n"
                f"Artist's mood before drawing: {intent.get('emotion', '')}\nWhat the artist wrote they wanted to show: {intent.get('text') or '(not written)'}\n"
                f"An assessor's notes on this task's focus dimensions (for you only — never pass scores on to the artist):\n{notes}\n\n"
                "Give your feedback."
            )
            system = SYSTEM_EN + (SYSTEM_SIMPLE_NOTE_EN if quest.get("ui") == "simple" else "")
            text = claude_text(system, [image_block(image_png), {"type": "text", "text": prompt}])
            return {"backend": self.name, "text": text}
        notes = "\n".join(f"- {_ZH[k]}：{dims[k]['note']}" for k in focus if k in dims)
        prompt = (
            f"任务：{quest['title']} —— {quest['prompt']}\n"
            f"创作者画前情绪：{intent.get('emotion', '')}\n创作者写下的意图：{intent.get('text') or '（未填写）'}\n"
            f"评估员对本任务重点维度的观察（仅供你参考，不要向创作者转述分数）：\n{notes}\n\n"
            "请给出你的反馈。"
        )
        system = SYSTEM + (SYSTEM_SIMPLE_NOTE if quest.get("ui") == "simple" else "")
        text = claude_text(system, [image_block(image_png), {"type": "text", "text": prompt}])
        return {"backend": self.name, "text": text}

    def compare(self, before_png: bytes, after_png: bytes, before_scores: Dict[str, Any], after_scores: Dict[str, Any],
                quest: Dict[str, Any], intent: Dict[str, Any]) -> Dict[str, Any]:
        if quest.get("lang") == "en":
            prompt = (
                f"Task: {quest['title']}\nArtist's intent: {intent.get('text') or '(not written)'}\n"
                "The first image is before the change, the second is after."
            )
            text = claude_text(
                COMPARE_SYSTEM_EN + (COMPARE_SYSTEM_SIMPLE_NOTE_EN if quest.get("ui") == "simple" else ""),
                [{"type": "text", "text": "Before:"}, image_block(before_png),
                 {"type": "text", "text": "After:"}, image_block(after_png),
                 {"type": "text", "text": prompt}],
            )
            return {"backend": self.name, "text": text}
        prompt = (
            f"任务：{quest['title']}\n创作者意图：{intent.get('text') or '（未填写）'}\n"
            "第一张图是修改前，第二张图是修改后。"
        )
        text = claude_text(
            COMPARE_SYSTEM + (COMPARE_SYSTEM_SIMPLE_NOTE if quest.get("ui") == "simple" else ""),
            [{"type": "text", "text": "修改前："}, image_block(before_png),
             {"type": "text", "text": "修改后："}, image_block(after_png),
             {"type": "text", "text": prompt}],
        )
        return {"backend": self.name, "text": text}
