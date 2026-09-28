"""界面语言：中文是源，英文是译。

这一层只回答两个问题：这次请求要哪种语言（`pick_lang`），以及把一份中文任务
换成英文任务（`quest_for`）。**中文任务本身一个字不动**——它们是研究刺激材料
（`missions.py`），英文版是并行的一份（`missions_en.py`），按 task_id / form_id /
condition 里的 ASCII 元数据还原出来，所以题库长了英文版跟着长，不用维护两份 id。

语言在建 session 的那一刻冻进 session（`lang` 字段），之后评分、反馈、陪伴都按它，
不再看请求头——孩子中途切了语言，这一次创作从头到尾仍然是一种语言。
"""
from typing import Any, Dict, List

LANGS = ("zh", "en")
DEFAULT = "zh"


def norm(value: str) -> str:
    v = (value or "").strip().lower()
    return "en" if v.startswith("en") else "zh" if v.startswith("zh") else ""


def pick_lang(request: Any) -> str:
    """`?lang=` 优先，其次 Accept-Language 的第一项；都没有就中文。"""
    try:
        q = norm(request.query_params.get("lang", ""))
        if q:
            return q
        first = (request.headers.get("accept-language") or "").split(",")[0].split(";")[0]
        return norm(first) or DEFAULT
    except Exception:
        return DEFAULT


def quest_for(quest: Dict[str, Any], lang: str) -> Dict[str, Any]:
    """英文会话拿英文任务；中文原样返回（同一个对象，不拷贝）。"""
    if not quest or norm(lang) != "en":
        return quest
    try:
        from .missions_en import translate_task
    except ImportError:               # 英文题库还没到位：退回中文，别把创作挡住
        return quest
    return translate_task(quest)


def families_for(fams: List[Dict[str, Any]], lang: str) -> List[Dict[str, Any]]:
    if norm(lang) != "en":
        return fams
    try:
        from .missions_en import translate_family
    except ImportError:
        return fams
    return [translate_family(f) for f in fams]


def say(lang: str, zh: str, en: str) -> str:
    """接口里那几句给孩子看的固定话（出错兜底之类）。"""
    return en if norm(lang) == "en" else zh
