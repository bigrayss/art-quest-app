"""Claude text feedback: observe → ask → suggest a direction (never an answer)."""
from typing import Any, Dict

from ..llm import claude_text, image_block
from ..scoring.base import DIMENSIONS

_ZH = {d["key"]: d["zh"] for d in DIMENSIONS}
_EN = {d["key"]: d["en"] for d in DIMENSIONS}

SYSTEM = """你是一位温和、好奇的美术教练，正在和一位 8–14 岁的创作者交流他们刚画完的作品。
硬性原则：
1. 帮助思考，不替代创作：不要告诉他们“应该画成什么样”，不给标准答案，不描述一张“更好的画”。
2. 优先使用观察、比较和提问；建议只给“方向”，不给“结果”。
3. 不提分数、不排名、不用“好/不好”评判整幅作品。
4. 以创作者自己写的意图为出发点：画面是否传达了他们想传达的？
5. 语气自然、具体、指向画面里真实存在的东西；不要空泛夸奖。
6. 中文，全文 120–180 字，分三段，用固定开头：「我看到：」「一个问题：」「可以试试：」。最后一段只提一个小的、可在几分钟内完成的修改方向。"""

COMPARE_SYSTEM = """你是一位美术教练。创作者根据一次反馈修改了作品，现在看到修改前后两张图。
用中文写 60–100 字：先指出你观察到的一处具体变化（不评价好坏），再问一个帮助他们自我判断的问题：修改后是否更接近他们最初的意图。不要提分数。"""

# 英文会话：同样的六条硬性原则，只换语言和长度。读者可能只有 6 岁，用词要简单。
SYSTEM_EN = """You are a gentle, curious art coach talking with a young artist (age 8–14) about the drawing they just finished.
Hard rules:
1. Help them think; never draw for them. Do not say what it "should" look like, give no model answer, describe no "better picture".
2. Prefer observing, comparing and asking. Suggestions give a direction, never a result.
3. No scores, no ranking, no "good/bad" verdict on the whole picture.
4. Start from the intent the artist wrote: does the picture show what they wanted to show?
5. Be natural and concrete; point at things that are really in the picture. No empty praise.
6. Simple English a 6-year-old can read. 80–120 words in three short paragraphs, each starting exactly with: "I see:", "One question:", "Try this:". The last paragraph names one small change that takes a few minutes."""

COMPARE_SYSTEM_EN = """You are an art coach. The artist changed their drawing after one round of feedback, and you now see the before and after.
Write 40–70 words in simple English: first point out one concrete change you notice (no judgement), then ask one question that helps them decide for themselves whether the change brought the picture closer to what they wanted at the start. No scores."""


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
            text = claude_text(SYSTEM_EN, [image_block(image_png), {"type": "text", "text": prompt}])
            return {"backend": self.name, "text": text}
        notes = "\n".join(f"- {_ZH[k]}：{dims[k]['note']}" for k in focus if k in dims)
        prompt = (
            f"任务：{quest['title']} —— {quest['prompt']}\n"
            f"创作者画前情绪：{intent.get('emotion', '')}\n创作者写下的意图：{intent.get('text') or '（未填写）'}\n"
            f"评估员对本任务重点维度的观察（仅供你参考，不要向创作者转述分数）：\n{notes}\n\n"
            "请给出你的反馈。"
        )
        text = claude_text(SYSTEM, [image_block(image_png), {"type": "text", "text": prompt}])
        return {"backend": self.name, "text": text}

    def compare(self, before_png: bytes, after_png: bytes, before_scores: Dict[str, Any], after_scores: Dict[str, Any],
                quest: Dict[str, Any], intent: Dict[str, Any]) -> Dict[str, Any]:
        if quest.get("lang") == "en":
            prompt = (
                f"Task: {quest['title']}\nArtist's intent: {intent.get('text') or '(not written)'}\n"
                "The first image is before the change, the second is after."
            )
            text = claude_text(
                COMPARE_SYSTEM_EN,
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
            COMPARE_SYSTEM,
            [{"type": "text", "text": "修改前："}, image_block(before_png),
             {"type": "text", "text": "修改后："}, image_block(after_png),
             {"type": "text", "text": prompt}],
        )
        return {"backend": self.name, "text": text}
