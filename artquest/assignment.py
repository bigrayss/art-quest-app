# -*- coding: utf-8 -*-
"""老师分工：每件画完的作品分给 K 位老师，老师只看分给自己的那些。

老师不可能评完全部作品，但研究要每件作品有 K 份独立评分（**默认 3**，用户 2026-09-30 定的「每個作品至少得被評過 3 次」）。
分工在这里自动做，规则只有一条：**谁手上最少，新作品先给谁**。

- 分配表 `data/assignments.json`：`{"raters_per_work": K, "works": {sid: [rater_id, ...]}}`。
- 老师打开列表时 `ensure()` 一次：没分满的作品补到 K 位。已经评过这件的老师先算进去
  （有人评了就是一份数据，不必再拉一位来凑），再从**没分到这件**的老师里按负担从少到多补。
- 新注册的老师从下一件新作品开始分到；已分满的作品不动，免得老师手上的名单变来变去。
- 研究员能改 K、能手动指定某件给谁（`set_work`）。
"""
import os
from typing import Any, Dict, Iterable, List, Optional

from .config import DATA_DIR
from .logstore import read_json, write_json

PATH = DATA_DIR / "assignments.json"
DEFAULT_RATERS_PER_WORK = 3


def _default_k() -> int:
    try:
        return max(1, int(os.environ.get("ARTQUEST_RATERS_PER_WORK", DEFAULT_RATERS_PER_WORK)))
    except ValueError:
        return DEFAULT_RATERS_PER_WORK


def load() -> Dict[str, Any]:
    data = read_json(PATH) or {}
    return {"raters_per_work": int(data.get("raters_per_work") or _default_k()),
            "works": {sid: list(r) for sid, r in (data.get("works") or {}).items()}}


def save(data: Dict[str, Any]) -> None:
    write_json(PATH, data)


def set_raters_per_work(k: int) -> Dict[str, Any]:
    data = load()
    data["raters_per_work"] = max(1, int(k))
    save(data)
    return data


def set_work(sid: str, rater_ids: Iterable[str]) -> Dict[str, Any]:
    """研究员手动指定：这件给这几位。空列表 = 收回，下次 ensure 再自动分。"""
    data = load()
    ids = [r for r in dict.fromkeys(rater_ids) if r]
    if ids:
        data["works"][sid] = ids
    else:
        data["works"].pop(sid, None)
    save(data)
    return data


def ensure(sids: Iterable[str], teacher_ids: List[str],
           graded: Optional[Dict[str, Iterable[str]]] = None) -> Dict[str, Any]:
    """把 `sids` 里没分满的作品补到 K 位老师。`graded[sid]` 是已经评过这件的老师，先算进去。
    返回整张分配表。没有老师就什么都不分。"""
    data = load()
    k = data["raters_per_work"]
    works = data["works"]
    graded = graded or {}
    load_of: Dict[str, int] = {t: 0 for t in teacher_ids}
    for raters in works.values():
        for r in raters:
            if r in load_of:
                load_of[r] += 1
    changed = False
    for sid in sids:
        have = list(dict.fromkeys(list(works.get(sid) or []) + [r for r in graded.get(sid, []) if r in load_of]))
        if have != list(works.get(sid) or []):
            for r in have:
                if r in load_of and r not in (works.get(sid) or []):
                    load_of[r] += 1
            works[sid] = have; changed = True
        if len(have) >= k or not teacher_ids:
            continue
        # 负担最少的先来；一样少按注册先后（teacher_ids 就是这个顺序），结果稳定
        pool = sorted((t for t in teacher_ids if t not in have), key=lambda t: (load_of[t], teacher_ids.index(t)))
        for t in pool[: k - len(have)]:
            have.append(t); load_of[t] += 1
        works[sid] = have; changed = True
    if changed:
        save(data)
    return data


def for_rater(data: Dict[str, Any], rater_id: str) -> List[str]:
    return [sid for sid, raters in data["works"].items() if rater_id in raters]
