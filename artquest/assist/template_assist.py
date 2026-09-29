"""没有 API key 时的陪伴。

模板容易写成正确的废话（「加油！」「你真棒！」），那和评价一样是在打分，
只是打的是高分。所以这里的句子都遵守同一条：**要么问一个他能接着想下去的
问题，要么把他自己写的意图还给他**。轮换而不是随机——同一次创作里连着
点两下得到同一句，比听起来更假。

话是说给 6 岁也能读的孩子：一句不超过 12 个字。简单版（quest["ui"] == "simple"）
只用最短的那几句。
"""
from typing import Any, Dict

# 顺着任何意图都能往下问的问题。不碰画面，只碰他脑子里的那个世界。
OPEN_QUESTIONS = [
    "它住的地方有什么声音？",
    "它会说话吗？想说什么？",
    "它今天过得怎么样？",
    "画外面还有什么？",
    "它最喜欢什么？画进去吗？",
    "这里是白天还是晚上？",
    "它有什么秘密？",
]

# 手上有他写的意图时，先把那句话还给他——他画到一半常常忘了自己要画什么。
WITH_INTENT = [
    "「{intent}」画到哪儿了？",
    "「{intent}」还想加什么？",
    "「{intent}」里，你最喜欢哪儿？",
]

ENCOURAGE = [
    "慢慢来。",
    "画错也没关系，接着画。",
    "这是你的画，怎么画都行。",
]

# 简单版：更短、更少
# 库要够大：连点六次不能听到同一句
OPEN_QUESTIONS_SIMPLE = [
    "这里是白天还是晚上？",
    "它今天过得怎么样？",
    "画外面还有什么？",
    "它住在哪儿？",
    "旁边还有谁？",
    "它在想什么？",
]
ENCOURAGE_SIMPLE = ["慢慢来。", "接着画。", "你想怎么画都行。"]

# 英文会话（quest["lang"] == "en"）用同样的三组、同样的轮换。规矩不变：
# 只问问题或把他的意图还给他，不评价、不夸、不给建议。
OPEN_QUESTIONS_EN = [
    "What sounds are around it?",
    "If it could talk, what would it say?",
    "How is its day going?",
    "What is outside the picture?",
    "What does it like best?",
    "Is it day or night here?",
    "Does it have a secret?",
]
WITH_INTENT_EN = [
    "How is “{intent}” going?",
    "What will you add to “{intent}”?",
    "Which part of “{intent}” do you like most?",
]
ENCOURAGE_EN = [
    "Take your time.",
    "A wrong line is fine. Keep going.",
    "It's your picture. Draw it your way.",
]
OPEN_QUESTIONS_SIMPLE_EN = [
    "Is it day or night here?",
    "How is its day going?",
    "What is outside the picture?",
    "Where does it live?",
    "Who else is there?",
    "What is it thinking?",
]
ENCOURAGE_SIMPLE_EN = ["Take your time.", "Keep going.", "Draw it any way you like."]


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
        simple = quest.get("ui") == "simple"
        with_intent = WITH_INTENT_EN if en else WITH_INTENT
        if simple:
            encourage = ENCOURAGE_SIMPLE_EN if en else ENCOURAGE_SIMPLE
            questions = OPEN_QUESTIONS_SIMPLE_EN if en else OPEN_QUESTIONS_SIMPLE
        else:
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
