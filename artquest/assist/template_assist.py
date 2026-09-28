"""没有 API key 时的陪伴。

模板容易写成正确的废话（「加油！」「你真棒！」），那和评价一样是在打分，
只是打的是高分。所以这里的句子都遵守同一条：**要么问一个他能接着想下去的
问题，要么把他自己写的意图还给他**。轮换而不是随机——同一次创作里连着
点两下得到同一句，比听起来更假。
"""
from typing import Any, Dict

# 顺着任何意图都能往下问的问题。不碰画面，只碰他脑子里的那个世界。
OPEN_QUESTIONS = [
    "它住的地方，会有什么声音？",
    "如果它会说话，第一句想说什么？",
    "它今天过得怎么样？",
    "画面外面还有什么，是我们看不见的？",
    "它最喜欢的东西，你打算画进去吗？",
    "这里是白天还是晚上？",
    "它身上有没有一个只有你知道的秘密？",
]

# 手上有他写的意图时，先把那句话还给他——他画到一半常常忘了自己要画什么。
WITH_INTENT = [
    "你说想画的是「{intent}」。现在画到哪儿了？",
    "想着「{intent}」这件事，接下来最想加的是什么？",
    "「{intent}」——这里面你最在意的是哪一块？",
]

ENCOURAGE = [
    "慢慢来，这张才刚开始。",
    "没有画错这回事，接着画。",
    "你想怎么画都可以，这是你的画。",
]

# 英文会话（quest["lang"] == "en"）用同样的三组、同样的轮换。规矩不变：
# 只问问题或把他的意图还给他，不评价、不夸、不给建议。
OPEN_QUESTIONS_EN = [
    "What sounds are there, where it lives?",
    "If it could talk, what would it say first?",
    "How is its day going?",
    "What is outside the picture, where we can't see?",
    "Its favourite thing — are you going to draw it in?",
    "Is it day or night here?",
    "Does it have a secret only you know?",
]
WITH_INTENT_EN = [
    "You said you wanted to draw \u201c{intent}\u201d. Where are you up to?",
    "Thinking about \u201c{intent}\u201d — what do you want to add next?",
    "\u201c{intent}\u201d — which part matters most to you?",
]
ENCOURAGE_EN = [
    "Take your time. This one is just getting started.",
    "There is no such thing as a wrong line. Keep going.",
    "You can draw it any way you like. It's your picture.",
]


# 孩子写心愿几乎都从「我想画」起头，模板句又是「你说你想画{intent}」——
# 直接拼就是「你说你想画我想画一个安静的房间」。把他那半句的起头剥掉再嵌。
INTENT_LEADS = ("我想要画", "我想画", "我要画", "我想要", "我想", "我要", "想画", "画一个", "画")
# 英文孩子写 "I want to draw a quiet room." ——同样把起头剥掉。长的在前，先匹配到的先剥。
INTENT_LEADS_EN = ("i want to draw", "i would like to draw", "i'd like to draw", "i am going to draw",
                   "i'm going to draw", "i want to make", "i want to", "i will draw", "i'll draw",
                   "i wanna draw", "draw", "drawing")
INTENT_TAILS = "。！!，,、 ."


def bare_intent(text: str) -> str:
    """「我想画一个安静的房间。」→「一个安静的房间」，能嵌进任何句式。
    "I want to draw a quiet room." → "a quiet room"。"""
    t = (text or "").strip()
    for lead in INTENT_LEADS:
        if t.startswith(lead) and len(t) > len(lead):
            t = t[len(lead):]
            break
    else:
        low = t.lower()
        for lead in INTENT_LEADS_EN:
            if low.startswith(lead + " ") and len(t) > len(lead) + 1:
                t = t[len(lead) + 1:]
                break
    return t.strip(INTENT_TAILS)


class TemplateAssist:
    backend = "template"

    def assist(self, image_png: bytes, quest: Dict[str, Any], intent: Dict[str, Any],
               nth: int = 1) -> Dict[str, Any]:
        want = bare_intent(intent.get("text") or "")
        i = max(0, nth - 1)
        en = quest.get("lang") == "en"
        with_intent = WITH_INTENT_EN if en else WITH_INTENT
        encourage = ENCOURAGE_EN if en else ENCOURAGE
        questions = OPEN_QUESTIONS_EN if en else OPEN_QUESTIONS
        # 第一次不提意图：前端已经把他自己写的那句话摆在窗口第一行了，
        # 这儿再说一遍就是复读，孩子会觉得这东西没在听。
        if want and i >= 2 and i % 2 == 0:
            text = with_intent[(i // 2) % len(with_intent)].format(intent=want)
        elif i % 3 == 2:
            text = encourage[(i // 3) % len(encourage)]
        else:
            text = questions[i % len(questions)]
        return {"text": text, "backend": self.backend}
