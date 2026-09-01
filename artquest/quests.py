"""Creative Quests — one task table that feeds both the game and the study.

A quest is what a child sees as a level on the treasure map; the same row is
what a researcher reads as a *task* (`task_id == quest.id`). Open-ended quests
simply take the permissive value of each research field — `reference: None`,
`time_limit_sec: None`, `allowed_tools: None` (= every tool) — which is a valid
condition value, not a missing field. Tighter, reference-driven tasks are just
rows with stricter values, so `user effect` and `task effect` stay separable
without a second task system.

Researchers can add or override tasks without touching code by dropping a JSON
list at `$ARTQUEST_DATA_DIR/tasks.json`; entries merge over the built-ins by id.

Each quest names the KidsArtBench dimensions it mainly activates (focus_dims)
so scoring and feedback can emphasise them (guide §02/§03).
"""
import json
import logging
from typing import Any, Dict, List, Optional

from .config import DATA_DIR

log = logging.getLogger("artquest")

# Every field a task carries, with the permissive default for open creation.
TASK_DEFAULTS: Dict[str, Any] = {
    "category": "open",        # research grouping: open / observation / skill / …
    "difficulty": 2,           # 1–5, researcher-assigned, never shown as a score
    "time_limit_sec": None,    # None = untimed
    "allowed_tools": None,     # None = every tool available
    "reference": None,         # None, or {"id", "file", "mode": "always|on_demand"}
    "hint": "",
    "focus_dims": [],
    "icon": "🎨",
    "color": "#e8632b",
    "enabled": True,
}

BUILTIN_QUESTS: List[Dict[str, Any]] = [
    {
        "id": "emotion_alone",
        "type": "情绪表达",
        "title": "画出「孤独」或「快乐」",
        "prompt": "不要直接画一张脸或表情。用颜色、空间、物体和构图，让整张画面本身传达「孤独」或「快乐」中的一种感觉。",
        "hint": "想一想：这种感觉是大的还是小的？是空旷的还是拥挤的？是冷的还是暖的？",
        "focus_dims": ["color_contrast", "picture_organization", "imagination"],
        "category": "emotion",
        "difficulty": 2,
        "icon": "🌗",
        "color": "#e8632b",
    },
    {
        "id": "imagine_animal",
        "type": "想象",
        "title": "设计一种不存在的动物",
        "prompt": "创造一种世界上没有的动物。它住在哪里？吃什么？有什么特别的本领？把它和它生活的地方画出来。",
        "hint": "可以把两三种你熟悉的动物或物体的特点组合起来，再改变大小和比例。",
        "focus_dims": ["imagination", "deformation", "transformation"],
        "category": "imagination",
        "difficulty": 2,
        "icon": "🦄",
        "color": "#7b4fd6",
    },
    {
        "id": "transform_chair",
        "type": "Transformation",
        "title": "一把椅子变成了……",
        "prompt": "从一把普通的椅子出发，把它变成一个完全不同用途的东西——交通工具、生物、建筑、乐器，都可以。让人还能认出它曾经是一把椅子。",
        "hint": "先想它的哪一部分保留，哪一部分改变，再决定它的新功能。",
        "focus_dims": ["transformation", "imagination", "line_combination"],
        "category": "transformation",
        "difficulty": 3,
        "icon": "🪑",
        "color": "#2b7de8",
    },
    {
        "id": "color_rain_city",
        "type": "Color / Composition",
        "title": "只用三种颜色画下雨的城市",
        "prompt": "选择三种颜色（黑白不算），只用这三种颜色画一座下雨的城市。想办法让画面有远近、有明暗、有雨的感觉。",
        "hint": "同一种颜色可以画得深一点或淡一点，也可以叠加。",
        "focus_dims": ["color_richness", "color_contrast", "picture_organization"],
        "category": "color",
        "difficulty": 3,
        "icon": "🌧️",
        "color": "#2e9e5b",
    },
    {
        "id": "story_character_home",
        "type": "Story",
        "title": "我的角色和它的家",
        "prompt": "创造一个属于你的角色，并画出它的家。家里应该能看出这个角色喜欢什么、害怕什么、每天在做什么。",
        "hint": "角色可以很小，家可以很大；或者相反。让物品替角色讲故事。",
        "focus_dims": ["picture_organization", "line_combination", "imagination"],
        "category": "story",
        "difficulty": 2,
        "icon": "🏠",
        "color": "#d9455f",
    },
]

CUSTOM_TASKS_PATH = DATA_DIR / "tasks.json"


def _normalize(task: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(TASK_DEFAULTS)
    out.update(task)
    out["task_id"] = out["id"]  # research-facing alias for the same row
    ref = out.get("reference")
    if isinstance(ref, dict):
        ref.setdefault("mode", "on_demand")
        ref.setdefault("id", f"{out['id']}_ref")
    return out


def _load_custom() -> List[Dict[str, Any]]:
    if not CUSTOM_TASKS_PATH.exists():
        return []
    try:
        data = json.loads(CUSTOM_TASKS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("ignoring %s: %s", CUSTOM_TASKS_PATH, e)
        return []
    return [t for t in data if isinstance(t, dict) and t.get("id")]


def load_quests() -> List[Dict[str, Any]]:
    """Built-ins merged with researcher-supplied tasks (custom wins on id)."""
    merged: Dict[str, Dict[str, Any]] = {q["id"]: dict(q) for q in BUILTIN_QUESTS}
    for t in _load_custom():
        merged[t["id"]] = {**merged.get(t["id"], {}), **t}
    return [_normalize(q) for q in merged.values() if _normalize(q)["enabled"]]


QUESTS: List[Dict[str, Any]] = load_quests()
QUESTS_BY_ID: Dict[str, Dict[str, Any]] = {q["id"]: q for q in QUESTS}


def get_quest(task_id: str) -> Optional[Dict[str, Any]]:
    return QUESTS_BY_ID.get(task_id)


def reload_quests() -> List[Dict[str, Any]]:
    """Re-read `tasks.json` (researchers edit it between runs)."""
    global QUESTS, QUESTS_BY_ID
    QUESTS = load_quests()
    QUESTS_BY_ID = {q["id"]: q for q in QUESTS}
    return QUESTS


EMOTIONS = ["开心", "平静", "兴奋", "紧张", "难过", "无聊", "好奇", "说不清"]
