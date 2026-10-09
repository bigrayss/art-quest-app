"""课后问卷：Post-use Structured Questionnaire v1.0（用户 2026-10-09 定稿）。

两件事放一份：**现在这个 app 用起来怎么样**（Part A，六题，UMUX-LITE / CSI / 系统专用条目改写）、
**以后的自适应 Agent 该怎么交互**（Part B，三题：主动权 / 主动帮助 / 个性化用哪些记录），
外加一道开放题。不是标准量表，论文里的定位是 literature-informed, system-specific
post-use questionnaire：A 部分六题各报分布，**不合成总分**；B 部分报各选项人数。

题目文本只在这里写一份：/api/config 发给界面，GET /opinions 连定义一起给研究员，
存下来的记录带 `instrument` 版本号——以后改一个字就换版本，旧数据照旧能读。
中文是键，英文在 static/lang/en.js。
"""
from __future__ import annotations

from typing import Any, Dict, List

INSTRUMENT = "post-use/1.0"

LIKERT = [(1, "非常不同意"), (2, "不同意"), (3, "一般"), (4, "同意"), (5, "非常同意")]
NA = "na"                       # 「没用过 / 说不清」：记下来，不计入评分
NA_LABEL = "没用过 / 说不清"

PARTS = [("A", "这个 App 用起来怎么样"), ("B", "以后的 AI 帮手"), ("C", "还想说的")]

ITEMS: List[Dict[str, Any]] = [
    # ---- Part A：当前系统体验。五点同意度 + 「没用过 / 说不清」 ----
    {"id": "q1", "part": "A", "type": "likert", "construct": "ease_of_use", "source": "UMUX-LITE",
     "zh": "我觉得这个 App 很容易使用。"},
    {"id": "q2", "part": "A", "type": "likert", "construct": "usefulness", "source": "UMUX-LITE",
     "zh": "这个 App 提供的功能能够满足我这次绘画的需要。"},
    {"id": "q3", "part": "A", "type": "likert", "construct": "exploration", "source": "CSI",
     "zh": "这个 App 让我能够尝试不同的绘画方法和想法。"},
    {"id": "q4", "part": "A", "type": "likert", "construct": "expressiveness", "source": "CSI",
     "zh": "这个 App 能帮助我画出自己想表达的内容。"},
    {"id": "q5", "part": "A", "type": "likert", "construct": "creative_agency", "source": "system-specific",
     "zh": "在创作过程中，我能够自己决定怎么画。"},
    {"id": "q6", "part": "A", "type": "likert", "construct": "help_accessibility", "source": "system-specific",
     "zh": "当我需要绘画帮助时，我能找到相应的功能或提示。"},
    # ---- Part B：未来 Agent 交互偏好 ----
    {"id": "q7", "part": "B", "type": "single", "construct": "task_initiative",
     "zh": "如果以后 AI 可以自动生成绘画主题，你更希望怎样开始一幅新作品？",
     "options": [("A", "我自己决定画什么。"),
                 ("B", "AI 推荐几个主题，由我选择。"),
                 ("C", "AI 直接生成一个主题，但我可以更换。"),
                 ("D", "AI 直接生成主题，我不需要再选择。"),
                 ("E", "不确定，要看具体情况。")]},
    {"id": "q8", "part": "B", "type": "single", "construct": "proactive_assistance",
     "zh": "如果未来 AI 可以在绘画过程中主动提供建议，你更希望它怎样做？",
     "options": [("A", "只有我主动请求时，AI 才提供建议。"),
                 ("B", "AI 可以显示一个小提示，由我决定是否查看。"),
                 ("C", "AI 可以直接显示建议。"),
                 ("D", "要看当时的情况。")]},
    {"id": "q9", "part": "B", "type": "multi", "construct": "personalization", "exclusive": ["F", "G"],
     "zh": "如果未来 AI 能根据你之前的绘画记录提供帮助，你希望它参考哪些信息？",
     "options": [("A", "我以前画过什么。"),
                 ("B", "我喜欢的绘画主题或风格。"),
                 ("C", "我以前遇到过哪些绘画困难。"),
                 ("D", "我完成过哪些绘画任务，以及完成情况。"),
                 ("E", "我以前接受或忽略过哪些 AI 建议。"),
                 ("F", "我不希望 AI 参考以前的记录。"),
                 ("G", "不确定。")]},
    # ---- Part C：开放反馈 ----
    {"id": "q10", "part": "C", "type": "open", "construct": "improvement",
     "zh": "如果只能改进这个 App 的一个地方，你最希望修改什么？为什么？"},
]
ITEM_IDS = [it["id"] for it in ITEMS]
OPEN_MAX = 2000


def definition() -> Dict[str, Any]:
    """界面和研究员都拿这一份：题目、选项、量表词。"""
    return {
        "instrument": INSTRUMENT,
        "parts": [{"key": k, "zh": v} for k, v in PARTS],
        "likert": [{"value": v, "zh": t} for v, t in LIKERT],
        "na": {"key": NA, "zh": NA_LABEL},
        "items": [{**{k: v for k, v in it.items() if k != "options"},
                   **({"options": [{"key": k, "zh": t} for k, t in it["options"]]} if "options" in it else {})}
                  for it in ITEMS],
    }


def clean(answers: Dict[str, Any]) -> Dict[str, Any]:
    """只留认识的题和合法的值；不合法的值报 ValueError（不是悄悄丢——那等于存了一份假的「没答」）。

    likert: 1–5 的整数或 "na"；single: 选项字母；multi: 选项字母的列表，F/G 只能单独出现；
    open: 字符串，截到 OPEN_MAX。空字符串 / 空列表 = 没答，不存。
    """
    out: Dict[str, Any] = {}
    by_id = {it["id"]: it for it in ITEMS}
    for key, val in (answers or {}).items():
        it = by_id.get(key)
        if it is None or val is None:
            continue
        t = it["type"]
        if t == "likert":
            if val == NA:
                out[key] = NA
            elif isinstance(val, bool) or not isinstance(val, int) or not 1 <= val <= 5:
                raise ValueError(f"{key}: 1–5 或 'na'，不是 {val!r}")
            else:
                out[key] = val
        elif t == "single":
            keys = {k for k, _ in it["options"]}
            if val == "":
                continue
            if val not in keys:
                raise ValueError(f"{key}: 没有选项 {val!r}")
            out[key] = val
        elif t == "multi":
            keys = [k for k, _ in it["options"]]
            if not isinstance(val, list):
                raise ValueError(f"{key}: 要一个列表")
            picked = [v for v in keys if v in val]          # 按选项顺序存，去重
            if len(picked) != len(set(val)):
                raise ValueError(f"{key}: 有不认识的选项")
            for ex in it.get("exclusive", []):
                if ex in picked and len(picked) > 1:
                    raise ValueError(f"{key}: {ex} 不能和别的选项一起选")
            if picked:
                out[key] = picked
        elif t == "open":
            s = str(val).strip()[:OPEN_MAX]
            if s:
                out[key] = s
    return out
