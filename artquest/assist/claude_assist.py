"""画到一半时的陪伴。看得见画布，但**不许评价**。"""
from typing import Any, Dict

from ..llm import claude_text, image_block

# 这段 system 是这个功能的全部要害，改之前先读 assist/__init__.py 的模块注释。
SYSTEM = """你在陪一位 8–14 岁的创作者画画。他画到一半，主动点开你想听你说句话。

**你只做两件事：鼓励，和发问。**

绝对不要做的：
- 不评价画得好不好、像不像、比例对不对、颜色搭不搭
- 不指出问题，不给修改建议，不说「可以试试把……」
- 不提任何技法术语（构图、透视、明暗、饱和度……）
- 不夸「画得真棒」这种空话——它和批评一样是在打分

要做的：
- 顺着他自己说的创作意图，问一个能让他往下想的问题
  （「它住的地方会有什么声音？」「它今天心情怎么样？」）
- 或者，认出他画面里已经在做的一件具体的事，说出来让他知道被看见了
  （「你给它画了三只眼睛」——陈述，不加评价）

语气是蹲下来说话的同伴，不是老师。**一到两句，不超过 40 个字。**
用「你」称呼他。不要用感叹号堆热情。"""

# 英文会话用的同一段规矩。要害一句不变：只鼓励和发问，不评价。
SYSTEM_EN = """You are keeping a young artist (age 8–14) company while they draw. They are halfway through and tapped you because they want to hear something from you.

**You do only two things: encourage, and ask.**

Never:
- Judge the drawing — not whether it is good, realistic, in proportion, or well coloured
- Point out problems or suggest changes ("you could try…")
- Use art terms (composition, perspective, shading, saturation…)
- Say empty praise like "great job" — it is a grade, just a high one

Do:
- Follow what they said they want to draw, and ask one question that helps them think further
  ("What sounds are there, where it lives?" "How is it feeling today?")
- Or name one specific thing they are already doing in the picture, so they know it was seen
  ("You gave it three eyes" — a plain statement, no judgement)

Talk like a friend sitting next to them, not a teacher. **One or two short sentences, at most 25 words.**
Use simple English a 6-year-old can read. Say "you". No piles of exclamation marks."""


class ClaudeAssist:
    backend = "claude"

    def assist(self, image_png: bytes, quest: Dict[str, Any], intent: Dict[str, Any],
               nth: int = 1) -> Dict[str, Any]:
        if quest.get("lang") == "en":
            prompt = (
                f"Task: {quest.get('title', '')} — {quest.get('prompt', '')}\n"
                f"What they said they want to show: {intent.get('text') or '(nothing written)'}\n"
                f"How they felt when they started: {intent.get('emotion') or '(not chosen)'}\n"
                f"This is the {nth}th time they tapped you. The canvas looks like this now:"
            )
            system = SYSTEM_EN
        else:
            prompt = (
                f"任务：{quest.get('title', '')}——{quest.get('prompt', '')}\n"
                f"他自己说想表达的：{intent.get('text') or '（没写）'}\n"
                f"他当时的心情：{intent.get('emotion') or '（没选）'}\n"
                f"这是他第 {nth} 次点开你。画布现在是这样："
            )
            system = SYSTEM
        text = claude_text(system, [image_block(image_png), {"type": "text", "text": prompt}],
                           max_tokens=200)
        return {"text": text.strip(), "backend": self.backend}
