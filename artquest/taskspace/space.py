# -*- coding: utf-8 -*-
"""`initialize()`：把来源、蓝图、候选、检查、材料装成一个任务空间，供选题 Agent 读。

它不选题、不评学生、不改库。返回的候选只带「可比较的属性」和「未解决的问题」；
「通过」只表示在规定范围内没发现未解决的一致性问题，不表示任务已经校准。
"""
from typing import Any, Callable, Dict, List, Optional

from ..missions import TASK_VERSION
from .blueprints import BLUEPRINTS, CAPABILITIES, GAPS, OPERATIONS
from .candidates import build_candidates
from .drafts import DRAFT_BLUEPRINTS, DRAFT_MATERIALS, build_draft_candidates
from .checks import FAIL, CONTRADICTS, BLOCKED, UNDET, INSUFFICIENT, rule_checks, semantic_checks
from .materials import MATERIALS, check_material
from .sources import EXCERPTS, SOURCES

TaskSpace = Dict[str, Any]


def initialize(include_legacy: bool = False,
               semantic_judge: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
               visual_judge: Optional[Callable[..., str]] = None) -> TaskSpace:
    cands = build_candidates(include_legacy=include_legacy)
    drafts = build_draft_candidates()
    mats: Dict[str, Dict[str, Any]] = {}
    for c in cands + drafts:
        issues = rule_checks(c) + semantic_checks(c, judge=semantic_judge)
        c["issues"] = issues
        c["status"] = _status(issues)
        mid = c["materials"].get("id")
        if mid and mid not in mats:
            mats[mid] = check_material(mid, judge=visual_judge)
        if mid:
            c["material_check"] = mats[mid]["status"]
    return dict(
        task_version=TASK_VERSION, capabilities=dict(CAPABILITIES), operations=dict(OPERATIONS),
        sources=SOURCES, excerpts=EXCERPTS, blueprints=BLUEPRINTS, gaps=GAPS,
        candidates=cands, materials=mats,
        drafts=dict(blueprints=DRAFT_BLUEPRINTS, candidates=drafts, materials=DRAFT_MATERIALS),
        summary=_summary(cands, mats),
    )


def _status(issues: List[Dict[str, Any]]) -> str:
    st = {i["status"] for i in issues if not i.get("advisory")}
    if FAIL in st or CONTRADICTS in st:
        return "blocked"          # 有明确矛盾：保持阻塞，不放宽规格让它通过
    if BLOCKED in st:
        return "blocked"
    if UNDET in st or INSUFFICIENT in st:
        return "open"             # 无法判断的内容保留未决
    return "clear"                # 没发现规定范围内的未解决问题——不是「已校准」


def _summary(cands: List[Dict[str, Any]], mats: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    by = {"clear": 0, "open": 0, "blocked": 0}
    for c in cands:
        by[c["status"]] += 1
    rules: Dict[str, int] = {}
    for c in cands:
        for i in c["issues"]:
            if i["status"] in (FAIL, CONTRADICTS, BLOCKED):
                rules[i["rule"]] = rules.get(i["rule"], 0) + 1
    return dict(candidates=len(cands), status=by, failing_rules=rules,
                materials={k: v["status"] for k, v in mats.items()})
