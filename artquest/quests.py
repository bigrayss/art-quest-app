# -*- coding: utf-8 -*-
"""The task table — one row, two readings.

A row is a **Creative Mission** to the child and an **experimental condition**
to the researcher; `task_id == quest.id` is the same key in both readings, so
the game and the study never drift apart.

Rows come from `missions.build_library()` (families M1–M9, see `missions.py`)
and can be added to or overridden by a researcher's `$ARTQUEST_DATA_DIR/tasks.json`
without touching code. Every row is validated at load: an unknown 9D dimension,
a dimension claimed as two roles at once, or a not-applicable dimension with no
reason stops the task from entering the library rather than producing data
nobody can interpret later.

Open creation is still expressible — it is simply the permissive value of every
research field (`stimulus: none`, `time_limit_sec: null`, `allowed_tools: null`)
— so `user effect` and `task effect` stay separable inside one table.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from .config import DATA_DIR, STATIC_DIR
from .missions import FAMILIES, TASK_VERSION, build_library
from .rubric import RubricError, applicable, normalize, summary

log = logging.getLogger("artquest")

# Every field a task carries, with the permissive default for open creation.
TASK_DEFAULTS: Dict[str, Any] = {
    "family": "", "family_slug": "", "family_name": "", "form_id": "",
    "version": TASK_VERSION, "prompt_style": "story",
    "category": "open", "difficulty": 2,
    "time_limit_sec": None,    # None = untimed
    "allowed_tools": None,     # None = every tool available
    "stimulus": {"kind": "none"},
    "reference": None,         # legacy view of a `reference` stimulus
    "phases": None,
    "condition": {},
    "process_targets": [],
    "research_goal": "",
    "hint": "", "icon": "🎨", "color": "#f79433", "enabled": True,
}

CUSTOM_TASKS_PATH = DATA_DIR / "tasks.json"
STIMULUS_MANIFEST = STATIC_DIR / "refs" / "manifest.json"


def _placeholder_ids() -> set:
    """Stimulus ids still served by a generated stand-in.

    A study run against a placeholder is not invalid data, it is *pilot* data —
    so it is marked, not blocked, and the flag travels into QC.
    """
    try:
        return set(json.loads(STIMULUS_MANIFEST.read_text(encoding="utf-8")).get("placeholders") or [])
    except (OSError, json.JSONDecodeError):
        return set()


def _normalize(task: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(TASK_DEFAULTS)
    out.update(task)
    tid = out.get("task_id") or out.get("id")
    out["task_id"] = out["id"] = tid
    # accept either name on the way in; both are present on the way out
    out["instruction"] = out.get("instruction") or out.get("prompt") or ""
    out["prompt"] = out["instruction"]
    out["title"] = out.get("title") or tid

    out["rubric"] = normalize(out.get("rubric"), task_id=tid)
    # the dimensions the task is built to elicit, for the scorer and the UI
    out["focus_dims"] = list(out["rubric"]["primary_dimensions"])
    out["applicable_dims"] = applicable(out["rubric"])
    out["rubric_summary"] = summary(out["rubric"])

    stim = out.get("stimulus") or {"kind": "none"}
    if stim.get("kind") == "reference" and not out.get("reference"):
        out["reference"] = {"id": stim.get("stimulus_id") or f"{tid}_ref",
                            "file": stim.get("file", ""), "mode": stim.get("mode", "always")}
    if out.get("reference") and not out["reference"].get("id"):
        out["reference"]["id"] = f"{tid}_ref"
    out["stimulus_id"] = stim.get("stimulus_id") or (out.get("reference") or {}).get("id") or ""
    if out["stimulus_id"] and out["stimulus_id"] in _PLACEHOLDERS:
        stim = dict(stim); stim["placeholder"] = True
        out["stimulus"] = stim
    out["stimulus_placeholder"] = bool((out.get("stimulus") or {}).get("placeholder"))
    return out


def _load_custom() -> List[Dict[str, Any]]:
    if not CUSTOM_TASKS_PATH.exists():
        return []
    try:
        data = json.loads(CUSTOM_TASKS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("ignoring %s: %s", CUSTOM_TASKS_PATH, e)
        return []
    return [t for t in data if isinstance(t, dict) and (t.get("task_id") or t.get("id"))]


def load_quests() -> List[Dict[str, Any]]:
    """The built-in library merged with researcher-supplied tasks (custom wins)."""
    merged: Dict[str, Dict[str, Any]] = {}
    for row in build_library():
        merged[row["task_id"]] = dict(row)
    for t in _load_custom():
        tid = t.get("task_id") or t.get("id")
        merged[tid] = {**merged.get(tid, {}), **t}

    out = []
    for tid, row in merged.items():
        try:
            task = _normalize(row)
        except RubricError as e:
            # a task nobody can interpret is worse than a missing task
            log.error("task %s rejected: %s", tid, e)
            continue
        if task["enabled"]:
            out.append(task)
    return out


def condition_snapshot(task: Dict[str, Any], *, app_version: str = "",
                       protocol: Optional[Dict[str, Any]] = None,
                       condition: Optional[Dict[str, Any]] = None,
                       task_order: Optional[int] = None) -> Dict[str, Any]:
    """The complete task definition **as this child actually saw it**.

    Frozen per session into `condition.json`. `tasks.json` will be edited and
    the library will grow; without this, a later reader would resolve a task_id
    against a definition the child never saw and silently misread the data.
    """
    stim = task.get("stimulus") or {"kind": "none"}
    return {
        "task_id": task["task_id"], "task_version": task.get("version", TASK_VERSION),
        "family": task.get("family", ""), "mission_family": task.get("family_slug", ""),
        "form_id": task.get("form_id", ""),
        "prompt_id": f"{task.get('family', '')}_{task.get('form_id', '')}".strip("_"),
        "prompt_style": task.get("prompt_style", ""),
        "title": task.get("title", ""), "instruction": task.get("instruction", ""),
        "hint": task.get("hint", ""),
        "stimulus": stim, "stimulus_id": task.get("stimulus_id", ""),
        "reference_id": (task.get("reference") or {}).get("id", ""),
        "time_limit_sec": task.get("time_limit_sec"),
        "allowed_tools": task.get("allowed_tools"),
        "phases": task.get("phases"),
        "task_condition": dict(task.get("condition") or {}),
        "rubric": task.get("rubric"),
        "process_targets": list(task.get("process_targets") or []),
        "study_condition": dict(condition or {}),
        "protocol": dict(protocol or {}),
        "task_order": task_order,
        "app_version": app_version,
    }


_PLACEHOLDERS = _placeholder_ids()
QUESTS: List[Dict[str, Any]] = load_quests()
QUESTS_BY_ID: Dict[str, Dict[str, Any]] = {q["id"]: q for q in QUESTS}


def get_quest(task_id: str) -> Optional[Dict[str, Any]]:
    return QUESTS_BY_ID.get(task_id)


def reload_quests() -> List[Dict[str, Any]]:
    """Re-read `tasks.json` and the stimulus manifest (edited between runs)."""
    global QUESTS, QUESTS_BY_ID, _PLACEHOLDERS
    _PLACEHOLDERS = _placeholder_ids()
    QUESTS = load_quests()
    QUESTS_BY_ID = {q["id"]: q for q in QUESTS}
    return QUESTS


def families() -> List[Dict[str, Any]]:
    """Family-level metadata, for protocols and for the map UI."""
    counts: Dict[str, int] = {}
    for q in QUESTS:
        counts[q.get("family", "")] = counts.get(q.get("family", ""), 0) + 1
    return [{"id": fid, "name": f["name"], "slug": f["slug"], "icon": f["icon"],
             "color": f["color"], "difficulty": f["difficulty"],
             "research_goal": f["research_goal"], "n_forms": counts.get(fid, 0)}
            for fid, f in FAMILIES.items()]


EMOTIONS = ["开心", "平静", "兴奋", "紧张", "难过", "无聊", "好奇", "说不清"]
