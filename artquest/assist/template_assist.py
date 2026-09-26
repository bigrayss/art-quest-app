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


# 孩子写心愿几乎都从「我想画」起头，模板句又是「你说你想画{intent}」——
# 直接拼就是「你说你想画我想画一个安静的房间」。把他那半句的起头剥掉再嵌。
INTENT_LEADS = ("我想要画", "我想画", "我要画", "我想要", "我想", "我要", "想画", "画一个", "画")
INTENT_TAILS = "。！!，,、 "


def bare_intent(text: str) -> str:
    """「我想画一个安静的房间。」→「一个安静的房间」，能嵌进任何句式。"""
    t = (text or "").strip()
    for lead in INTENT_LEADS:
        if t.startswith(lead) and len(t) > len(lead):
            t = t[len(lead):]
            break
    return t.strip(INTENT_TAILS)


class TemplateAssist:
    backend = "template"

    def assist(self, image_png: bytes, quest: Dict[str, Any], intent: Dict[str, Any],
               nth: int = 1) -> Dict[str, Any]:
        want = bare_intent(intent.get("text") or "")
        i = max(0, nth - 1)
        # 第一次不提意图：前端已经把他自己写的那句话摆在窗口第一行了，
        # 这儿再说一遍就是复读，孩子会觉得这东西没在听。
        if want and i >= 2 and i % 2 == 0:
            text = WITH_INTENT[(i // 2) % len(WITH_INTENT)].format(intent=want)
        elif i % 3 == 2:
            text = ENCOURAGE[(i // 3) % len(ENCOURAGE)]
        else:
            text = OPEN_QUESTIONS[i % len(OPEN_QUESTIONS)]
        return {"text": text, "backend": self.backend}
