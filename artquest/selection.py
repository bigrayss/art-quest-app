"""选题的服务端规则（agent 级数据计划 PR 3，2026-10-14）。**影子**：只算、只记，不改孩子看到的任何东西。

今天地图上摆哪几道题是 app.js `renderQuests()` 在浏览器里算的，服务器只在建 session 时收到一个 quest_id。
这里把同一套规则复刻到服务端，用**服务端已保存的数据**（这个身份做完了哪些）当依据，算出：

    冻结候选 candidates  → 当时合法的题（版本、家族、是不是锚定题、做过没有）
    实际排位 offered     → 五个待办位上按规则该摆的题（protocol 模式是整条序列）

客户端渲染完地图把自己摆的那几道报上来（client_offered），服务端比一比（same_set / same_order），
两边都记进一张 `prepared` 票里（见 storage.prepare_decision）。影子阶段**客户端仍是权威**：
它比不出 Math.random 抽到哪道（老地图的家族随机），只比集合和顺序。切换权威是 PR 4 的事。

规则版本 RULES_VERSION 跟着这里的实现走：规则一变就升，决策记录里带着它，分析时分得开。
四个入口（entrypoint）各有各的规则，统一的是候选怎么算、记录长什么样：

    map        首访任务库：本段五道 + 画完一张开一个 M 族（UNLOCK_ORDER 轮转），五个待办位
               不在首访模式：十个家族，每家族一道**没做过**的（客户端随机抽——这里给池子）
    protocol   研究协议定的整条序列（study.py 已经在服务端算好了），只是记下来
    growth     成长面板「去 X 练习」：按主考维度找家族，没去过的优先，M0 兜底
"""
import random
import uuid
from typing import Any, Dict, Iterable, List, Optional, Set

from . import missions_bank
from .quests import QUESTS, QUESTS_BY_ID, TASK_VERSION

RULES_VERSION = "rules/v1"       # 复刻 app.js renderQuests / randomForm / recommendFor 2026-10-12 版
PENDING_SLOTS = 5
# 画完几张就多开几个地方：顺序固定，先讲故事、换颜色这些门槛低的，再到规则世界（和 app.js 同一份）
UNLOCK_ORDER = ["M9", "M6", "M3", "M4", "M5", "M1", "M2", "M7", "M8", "M0"]
ENTRYPOINTS = ("map", "protocol", "growth")
TIER = "simple"                  # 只剩简单版（2026-10-12）


def identity_key(who: Dict[str, Any]) -> str:
    """决策绑的是**有效身份**，强的优先：研究代号 > 账号 > 设备。换了人就换 key（共用 iPad 上尤其要紧）。"""
    who = who or {}
    if who.get("participant_id"):
        return f"pid:{who['participant_id']}"
    if who.get("account_id"):
        return f"acc:{who['account_id']}"
    if who.get("anon_id"):
        return f"anon:{who['anon_id']}"
    return ""


def tier_forms(family: str, tier: str = TIER) -> List[Dict[str, Any]]:
    """这个家族在地图上能出现的题（库里的顺序）：非 legacy、带这个版本。= app.js tierForms。"""
    return [q for q in QUESTS if q.get("family") == family and not q.get("legacy") and tier in (q.get("tiers") or [])]


def bank_forms(band_id: str) -> List[Dict[str, Any]]:
    """首访任务库里这个年龄段的五道，按 OB/ST/FG/TR/DS 的顺序。= app.js bankForms。"""
    order = missions_bank.ORDER
    rows = [q for q in QUESTS if q.get("bank") and q.get("band") == band_id]
    return sorted(rows, key=lambda q: order.index(q["family"]) if q["family"] in order else len(order))


def families() -> List[str]:
    """老地图上的十个家族（有简单版题的才算），库里的顺序。"""
    seen: List[str] = []
    for q in QUESTS:
        f = q.get("family", "")
        if f and not q.get("bank") and not q.get("legacy") and f not in seen and tier_forms(f):
            seen.append(f)
    return seen


def _cand(q: Dict[str, Any], done: Set[str], **extra: Any) -> Dict[str, Any]:
    return {"task_id": q["id"], "family": q.get("family", ""), "bank": q.get("bank") or "",
            "band": q.get("band") or "", "tiers": list(q.get("tiers") or []), "anchor": bool(q.get("anchor")),
            "version": q.get("version", ""), "done": q["id"] in done, **extra}


def compute(entrypoint: str, who: Dict[str, Any], done_ids: Iterable[str], *,
            age: Optional[int] = None, age_source: str = "", first_visit: bool = True,
            sequence: Optional[List[str]] = None, seq_index: int = 0, dim: str = "",
            tier: str = TIER) -> Dict[str, Any]:
    """按规则算一次「该摆什么」。纯函数：输入全在参数里，所以记下来就能复现。"""
    done = set(done_ids or [])
    entrypoint = entrypoint if entrypoint in ENTRYPOINTS else "map"
    out: Dict[str, Any] = {
        "decision_id": "", "authority": "shadow", "rules_version": RULES_VERSION,
        "task_version": TASK_VERSION, "bank_version": missions_bank.BANK_VERSION,
        "entrypoint": entrypoint, "rule": "", "identity": {k: (who or {}).get(k, "") for k in ("participant_id", "account_id", "anon_id")},
        "identity_key": identity_key(who), "history": {"done_task_ids": sorted(done), "n_done": len(done), "source": "server"},
        "routing": {"age": age, "age_source": age_source, "band": ""}, "candidates": [], "offered": [],
        "locked_more": False, "gate": "", "note": "",
    }

    if entrypoint == "protocol" or sequence:
        seq = [t for t in (sequence or []) if t in QUESTS_BY_ID]
        out["rule"] = "protocol"
        out["candidates"] = [_cand(QUESTS_BY_ID[t], done, position=i) for i, t in enumerate(seq)]
        out["offered"] = [{"position": i, "task_id": t, "family": QUESTS_BY_ID[t].get("family", ""),
                           "locked": i != seq_index, "finished": t in done} for i, t in enumerate(seq)]
        return out

    if entrypoint == "growth":
        out["rule"] = "recommend_for"
        fams = [f for f in families() if f != "M0" and any(
            dim in ((q.get("rubric") or {}).get("primary_dimensions") or []) for q in tier_forms(f, tier))]
        if not fams:
            fams = [f for f in families() if f == "M0"]
        been = {t.split("_")[0] for t in done}
        pick = next((f for f in fams if f not in been), fams[0] if fams else "")
        out["routing"]["dim"] = dim
        for f in fams:
            forms = tier_forms(f, tier)
            left = [q for q in forms if q["id"] not in done] or forms
            out["candidates"].extend(_cand(q, done, in_pool=q in left) for q in forms)
            out["offered"].append({"position": fams.index(f), "family": f, "task_id": None,
                                   "pool": [q["id"] for q in left], "picked": f == pick, "locked": False, "finished": False})
        out["note"] = "the client draws one form at random from the picked family's pool"
        return out

    # entrypoint == "map"
    band = missions_bank.band_of(age) if first_visit else {}
    if first_visit and age is None:
        out["rule"] = "bank_rotation"
        out["gate"] = "age"                       # 年龄门：没年龄不往下走，地图是空的
        return out
    if first_visit and band:
        out["rule"] = "bank_rotation"
        out["routing"]["band"] = band["id"]
        sequence_q = list(bank_forms(band["id"]))
        per_fam = {f: tier_forms(f, tier) for f in UNLOCK_ORDER}
        for rnd in range(5):
            for f in UNLOCK_ORDER:
                if rnd < len(per_fam[f]):
                    sequence_q.append(per_fam[f][rnd])
        pending, finished, rest = [], [], 0
        for q in sequence_q:
            if q["id"] in done:
                finished.append(q)
            elif len(pending) < PENDING_SLOTS:
                pending.append(q)
            else:
                rest += 1
        out["candidates"] = [_cand(q, done, position=i) for i, q in enumerate(sequence_q)]
        out["offered"] = [{"position": i, "task_id": q["id"], "family": q.get("family", ""), "locked": False, "finished": False}
                          for i, q in enumerate(pending)]
        out["finished"] = [q["id"] for q in finished]
        out["locked_more"] = rest > 0
        return out

    # 老地图：十个家族，每家一道没做过的（客户端随机抽，这里给池子）
    out["rule"] = "family_random"
    if first_visit and age is not None and not band:
        out["routing"]["band"] = ""
        out["note"] = "age out of the bank's range: back to the family map"
    for i, f in enumerate(families()):
        forms = tier_forms(f, tier)
        left = [q for q in forms if q["id"] not in done] or forms
        out["candidates"].extend(_cand(q, done, in_pool=q in left) for q in forms)
        out["offered"].append({"position": i, "family": f, "task_id": None, "pool": [q["id"] for q in left],
                               "locked": False, "finished": all(q["id"] in done for q in forms)})
    return out


def offered_keys(decision: Dict[str, Any]) -> List[str]:
    """客户端报上来的是它摆的卡的 key：具体题是 task_id，家族卡是家族 id。拿同样的形状来比。"""
    return [o.get("task_id") or o.get("family") or "" for o in decision.get("offered") or []]


def compare(decision: Dict[str, Any], client_offered: List[str]) -> Dict[str, Any]:
    """影子对照：集合一样吗、顺序一样吗。老地图的随机抽比不出，只比家族集合。"""
    mine = offered_keys(decision)
    theirs = list(client_offered or [])
    if decision.get("rule") == "protocol":
        theirs = theirs or []
    return {"same_set": set(mine) == set(theirs), "same_order": mine == theirs,
            "server_n": len(mine), "client_n": len(theirs),
            "only_server": sorted(set(mine) - set(theirs)), "only_client": sorted(set(theirs) - set(mine))}


def new_decision_id(ticket_sid: str) -> str:
    """decision_id 里带着它住的那张票的 id，查找不用扫目录。"""
    return f"dec_{ticket_sid}_{uuid.uuid4().hex[:6]}"


def ticket_of(decision_id: str) -> str:
    parts = (decision_id or "").split("_")
    return parts[1] if len(parts) == 3 and parts[0] == "dec" else ""


def history_key(decision: Dict[str, Any]) -> str:
    """同一个身份、同样的历史、同样的入口和路由 → 同一个决策（幂等），不每次进地图就开一张新票。"""
    h = decision.get("history") or {}
    r = decision.get("routing") or {}
    return "|".join([decision.get("rules_version", ""), decision.get("task_version", ""), decision.get("bank_version", ""),
                     decision.get("entrypoint", ""), decision.get("rule", ""), str(r.get("age")), r.get("band", "") or "",
                     r.get("dim", "") or "", ",".join(h.get("done_task_ids") or []),
                     ",".join(o.get("task_id") or o.get("family") or "" for o in decision.get("offered") or [])])


def draw_picks(decision: Dict[str, Any], rng: Optional[random.Random] = None) -> Dict[str, str]:
    """权威在服务端时，老地图 / 成长面板那一下「随机抽一道」也在这里抽：每个有池子的位置抽一道。
    一次展示抽一次（挂在 offer 上，不挂在决策上）——「每次进地图重新抽」这条用户要的行为不变。"""
    rng = rng or random
    picks: Dict[str, str] = {}
    for o in decision.get("offered") or []:
        pool = o.get("pool") or []
        if pool and not o.get("task_id"):
            picks[o.get("family", "")] = rng.choice(pool)
    return picks


def cards_for_client(decision: Dict[str, Any], picks: Dict[str, str]) -> Dict[str, Any]:
    """发给浏览器摆的那份：它只负责画出来和收点击。形状贴着 renderQuests 里的 card。"""
    return {"rule": decision.get("rule"), "gate": decision.get("gate", ""), "locked_more": bool(decision.get("locked_more")),
            "finished": list(decision.get("finished") or []),
            "offered": [{"key": o.get("task_id") or o.get("family") or "", "task_id": o.get("task_id") or picks.get(o.get("family", "")),
                         "family": o.get("family", ""), "locked": bool(o.get("locked")), "finished": bool(o.get("finished")),
                         "picked": bool(o.get("picked"))} for o in decision.get("offered") or []],
            "picks": dict(picks)}
