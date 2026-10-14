# -*- coding: utf-8 -*-
"""候选：库里每一道 v2 题在蓝图下的完整描述——文案、属性、固定条件、自由空间、来源关系、材料规格。
缺一项就还不是完整候选（Step 2 的结束条件）。

属性首先服务 Agent 理解，不评价题目好坏：在遇到具体学生之前就能描述（DECISIVE 的属性 / 偏好分离），
不因为某个学生喜欢它就改变它的含义。

九维关联每条都带理由、成立条件和「孩子能不能合理地绕开」——一道允许用单色线稿完成、目标又不依赖颜色的题，
不能因为「允许使用颜色」就标 Color 关联（Step 3.3）。这里**不改** `missions.FAMILIES` 的 rubric，只把
family 的 primary / secondary 翻译成带条件的关联，并把「可绕开」的标出来供检查报告。
"""
import hashlib
import re
from typing import Any, Dict, List, Optional

from ..missions import FAMILIES, TASK_VERSION, build_library
from .blueprints import BLUEPRINTS
from .materials import MATERIALS, NONE
from .sources import PROJECT
from .task_sources import TASK_RELATIONS

# family → 维度 → (理由, 成立条件, 可被合理绕开？)
# 「可绕开」= 学生可以合理完成任务却完全不产生这项表现，而且任务目标也不依赖它
DIM_NOTES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "M1": {
        "realism": dict(why="要求照着图把每样东西画在原位、大小一致", holds_if="参考图常显且文案要求原位", bypass=False),
        "picture_organization": dict(why="整幅场景的大块与小东西的安排由参考图给定，画面组织被直接比较", holds_if="同上", bypass=False),
        "line_combination": dict(why="只有铅笔 + 橡皮，形体靠线条组织", holds_if="allowed_tools 不含笔刷", bypass=False),
        "line_texture": dict(why="铅笔线的粗细与力度可观察", holds_if="同上", bypass=True),
    },
    "M2": {
        "realism": dict(why="大小、前后、遮挡要画准", holds_if="4 物体 · 2 遮挡规格成立", bypass=False),
        "picture_organization": dict(why="少量物体的空间关系就是画面组织", holds_if="同上", bypass=False),
        "line_combination": dict(why="铅笔线稿", holds_if="allowed_tools 不含笔刷", bypass=False),
        "line_texture": dict(why="铅笔线的变化", holds_if="同上", bypass=True),
    },
    "M3": {
        "imagination": dict(why="碎片变成什么由孩子决定", holds_if="碎片印在画布上、文案不规定变成什么", bypass=False),
        "transformation": dict(why="抽象碎片被转化为有意义的形象", holds_if="同上", bypass=False),
        "picture_organization": dict(why="要把分散的碎片整合进一幅画", holds_if="文案要求「完整的画」", bypass=False),
        "deformation": dict(why="碎片可被夸张 / 改造", holds_if="—", bypass=True),
        "line_combination": dict(why="接着已有线条画", holds_if="—", bypass=True),
    },
    "M4": {
        "deformation": dict(why="物品的结构被改变", holds_if="文案要求改造", bypass=False),
        "transformation": dict(why="从一种功能转成另一种功能", holds_if="目标功能由题给定", bypass=False),
        "imagination": dict(why="改造方案的新颖程度", holds_if="—", bypass=False),
        "picture_organization": dict(why="单件物品的画面安排", holds_if="—", bypass=True),
        "line_combination": dict(why="结构线条", holds_if="—", bypass=True),
    },
    "M5": {
        "transformation": dict(why="两个概念被合成一个新东西", holds_if="文案要求合为一体", bypass=False),
        "deformation": dict(why="概念各自的形被改动才能连成一体", holds_if="文案禁止只贴上去", bypass=False),
        "imagination": dict(why="融合方式的新颖程度", holds_if="—", bypass=False),
        "picture_organization": dict(why="融合物的画面安排", holds_if="—", bypass=True),
    },
    "M6": {
        "color_richness": dict(why="任务目标就是用颜色传达气氛", holds_if="文案要求只改颜色和明暗", bypass=False),
        "color_contrast": dict(why="明暗与冷暖对比是传达气氛的手段", holds_if="同上", bypass=False),
        "picture_organization": dict(why="重画场景时的布局", holds_if="参考图常显", bypass=True),
        "line_texture": dict(why="可观察但目标不依赖", holds_if="—", bypass=True),
    },
    "M7": {
        "line_combination": dict(why="第一步只用线条表达概念", holds_if="文案要求第一步只用线条", bypass=False),
        "line_texture": dict(why="线的力度、粗细、快慢", holds_if="同上", bypass=False),
        "transformation": dict(why="第二步把抽象线发展成有内容的画", holds_if="文案要求不擦掉第一步的线", bypass=False),
        "imagination": dict(why="线变成什么", holds_if="同上", bypass=False),
        "picture_organization": dict(why="最终画面的组织", holds_if="—", bypass=True),
    },
    "M8": {
        "imagination": dict(why="在规则下构想一个世界", holds_if="规则在画里成立", bypass=False),
        "transformation": dict(why="抽象规则被转成可见的生活场景", holds_if="同上", bypass=False),
        "picture_organization": dict(why="一个世界里的多个要素要组织起来", holds_if="文案要求「一天的生活 / 发生的事」", bypass=False),
        "realism": dict(why="可观察", holds_if="—", bypass=True),
        "deformation": dict(why="规则常要求变形（人比虫子小）", holds_if="规则涉及尺度", bypass=True),
        "color_richness": dict(why="允许上色但目标不依赖颜色", holds_if="—", bypass=True),
        "color_contrast": dict(why="同上", holds_if="—", bypass=True),
        "line_combination": dict(why="可观察", holds_if="—", bypass=True),
        "line_texture": dict(why="可观察", holds_if="—", bypass=True),
    },
    "M9": {
        "imagination": dict(why="故事接下来发生什么由孩子决定", holds_if="故事开头开放", bypass=False),
        "picture_organization": dict(why="叙事画面要安排人物与场景", holds_if="文案要求画出「发生的事 / 情景」", bypass=False),
        "transformation": dict(why="文字开头转成画面", holds_if="—", bypass=True),
        "color_richness": dict(why="允许上色但目标不依赖颜色（可单色线稿完成）", holds_if="—", bypass=True),
        "line_combination": dict(why="可观察", holds_if="—", bypass=True),
    },
    "M0": {},
}

# 题面里出现、而蓝图没有的具体条件（Step 1.3：项目新增条件必须说用途）
_TASK_ADDED: Dict[str, List[Dict[str, str]]] = {
    "M4_J3": [dict(requirement="还要看得出鞋子的样子", relation=PROJECT, purpose="把 base_form_preservation 写进文案，初中版显式化")],
    "M4_J4": [dict(requirement="至少能救两个人", relation=PROJECT, purpose="初中版加一条功能条件，让「救援机器」的功能构想具体化")],
    "M5_A2": [dict(requirement="不只是把花贴上去，要让两者连成一体", relation=PROJECT, purpose="禁止并置，这是 conceptual integration 的定义")],
    "M5_E4": [dict(requirement="不要只把鲨鱼贴在书包上", relation=PROJECT, purpose="同上")],
    "M5_J5": [dict(requirement="不只是把学校放在鲸鱼背上", relation=PROJECT, purpose="同上")],
    "M6_A2": [dict(requirement="不加新的怪物", relation=PROJECT, purpose="把「吓人」限制在颜色和明暗上")],
}


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _materials_of(row: Dict[str, Any]) -> Dict[str, Any]:
    stim = row.get("stimulus") or {"kind": "none"}
    if stim.get("kind") == "reference":
        return dict(kind="reference", id=stim["stimulus_id"], mode=stim.get("mode", "always"),
                    spec=MATERIALS.get(stim["stimulus_id"]))
    if stim.get("kind") == "fragments":
        return dict(kind="fragments", id=stim["stimulus_id"], spec=MATERIALS.get(stim["stimulus_id"]))
    return dict(NONE)


_COUNT_WORDS = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5}


def required_outputs(text: str) -> int:
    """文案要求产出几件：「画出两种 / 三个方案 / 两张」→ >1；默认 1。只看产出词，不看「两条规则 / 两个人」。"""
    m = re.search(r"([一两二三四五])(种|个|张|幅)[^。，；]{0,6}?(方案|草图|布局|画|设计|想法|构想)", text)
    if m:
        return _COUNT_WORDS[m.group(1)]
    return 1


def _added_conditions(row: Dict[str, Any]) -> List[Dict[str, str]]:
    fam, cond = row["family"], row.get("condition", {})
    out = list(_TASK_ADDED.get(row["task_id"], []))
    if fam == "M8":
        for r in cond.get("rules", []):
            out.append(dict(requirement=f"规则：{r}", relation=PROJECT, purpose="world-rule generator 的约束，记进 condition.rules"))
        if cond.get("challenge"):
            out.append(dict(requirement=f"可选：{cond['challenge']}", relation=PROJECT, purpose="初中版可选第三条；可选项不进必要产出"))
    elif fam == "M4":
        out.append(dict(requirement=f"基础物 {cond.get('base_object')} → {cond.get('goal')}" + (f" @ {cond.get('environment')}" if cond.get("environment") else ""),
                        relation=PROJECT, purpose="三张卡组合：换题材、保持操作"))
    elif fam == "M5":
        out.append(dict(requirement=f"概念对 {cond.get('concept_a')} + {cond.get('concept_b')}", relation=PROJECT, purpose="概念对由项目挑选"))
    elif fam == "M6":
        out.append(dict(requirement=f"目标气氛 {cond.get('mood')}", relation=PROJECT, purpose="颜色要传达的东西由题给定"))
    elif fam == "M7":
        out.append(dict(requirement=f"概念 {cond.get('concept')}", relation=PROJECT, purpose="线条要表达的概念由题给定"))
    elif fam == "M3":
        out.append(dict(requirement=f"碎片组 {cond.get('fragment_seed')}", relation=PROJECT, purpose="五组平行碎片"))
    return out


def _variation(row: Dict[str, Any], anchor: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """和同家族第一道锚定题比：改变了什么、保持了什么（WorkArena++ 的「同任务不同配置」）。"""
    if anchor is None or anchor["task_id"] == row["task_id"]:
        return dict(against=None, changed=[], kept=["（锚定题本身）"])
    changed, kept = [], ["操作", "产出数量", "工具"]
    a_stim, r_stim = anchor.get("stimulus") or {}, row.get("stimulus") or {}
    if a_stim.get("stimulus_id") != r_stim.get("stimulus_id"):
        changed.append("材料")
    else:
        kept.append("材料")
    for k in sorted(set(anchor.get("condition", {})) | set(row.get("condition", {}))):
        if k in ("tiers", "anchor"):
            continue
        if anchor["condition"].get(k) != row["condition"].get(k):
            changed.append(f"condition.{k}")
    changed.append("题材 / 叙事")
    if row["tiers"] != anchor["tiers"]:
        changed.append(f"版本 {row['tiers']}")
    return dict(against=anchor["task_id"], changed=changed, kept=kept)


def build_candidates(include_legacy: bool = False) -> List[Dict[str, Any]]:
    rows = [r for r in build_library() if include_legacy or not r.get("legacy")]
    first_anchor: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if (r.get("anchor") or (r.get("bank") and r.get("band") == "B1")) and r["family"] not in first_anchor:
            first_anchor[r["family"]] = r
    out: List[Dict[str, Any]] = []
    for r in rows:
        fam = r["family"]
        bp_id = f"BP_{fam}"
        bp = BLUEPRINTS[bp_id]
        rub = r.get("rubric") or {}
        demoted = dict(r.get("rubric_overrides") or {})      # 2026-10-11 实例级降级：原角色 / 新角色 / 反例
        dims = []
        if r.get("bank"):
            # 首访任务库：理由随行带着（docs 里每道题的「九维关联」），关注 = primary、探索性 = exploratory；
            # 文档每条都写了成立条件（「只有学生主动用色时」），所以不另判可绕开——exploratory 本来就不是任务的要求
            for d in r.get("dim_notes") or []:
                dims.append(dict(dim=d["key"], relation=d["role"], why=d["why"], holds_if="见理由", bypass=(d["role"] != "primary")))
        for role in (() if r.get("bank") else ("primary", "secondary")):
            for d in rub.get(f"{role}_dimensions", []) or []:
                note = dict(DIM_NOTES.get(fam, {}).get(d, dict(why="（未写理由）", holds_if="", bypass=None)))
                if role == "secondary" and note.get("bypass") and d not in demoted:
                    # 家族层面可绕开、但这道题被例外保留（M8 尺度规则）：在这道题上不可绕开
                    note["bypass"] = False
                    note["why"] += "；这道题的规则涉及尺度，保留 secondary"
                dims.append(dict(dim=d, relation=role, **note))
        added = _added_conditions(r)
        if r.get("bank"):
            added = [dict(requirement=f"必要条件：{r['requirements']}", relation=PROJECT, purpose="与题面一致的内容条件（文档「必要条件」）")] + \
                    [dict(requirement=f"提示 {h['id']}：{h['text']}", relation=PROJECT, purpose="按需显示的过程支持，不是必要条件") for h in r.get("hints") or []]
        text = r["instruction"]
        out.append(dict(
            task_id=r["task_id"], family=fam, blueprint=bp_id, tiers=list(r["tiers"]), anchor=bool(r.get("anchor")),
            copy=dict(title=r["title"], instruction=text, hint=r.get("hint", ""), version=r.get("version", TASK_VERSION), sha=_sha(text)),
            operation=bp["operation"], content=list(bp["content"]),
            outputs=dict(count=bp["outputs"]["count"], form=bp["outputs"]["form"], required_by_copy=required_outputs(text)),
            inputs=dict(bp["inputs"]),
            fixed=list(bp["invariants"]) + [a["requirement"] for a in added],
            free=list(bp["free"]),
            bank=r.get("bank", ""), band=r.get("band", ""), hints=list(r.get("hints") or []), requirements=r.get("requirements", ""),
            load=dict(bp["load"]),
            # 三层：家族共同（蓝图）→ 本题专属（task_sources，按题面写）→ 题面自己的新增条件
            source_relations=[dict(x, scope="family") for x in bp["source_relations"]]
                             + [dict(x, scope="task") for x in TASK_RELATIONS.get(r["task_id"], [])]
                             + [dict(x, scope="task") for x in added],
            dims=dims, demoted=demoted,
            materials=_materials_of(r),
            condition=dict(r.get("condition", {})),
            allowed_tools=r.get("allowed_tools"), time_limit_sec=r.get("time_limit_sec"), phases=r.get("phases"),
            variation=_variation(r, first_anchor.get(fam)),
        ))
    return out
