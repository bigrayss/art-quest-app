# -*- coding: utf-8 -*-
"""检查：对象是六样东西之间的具体关系（来源、蓝图、学生文案、任务属性、必要产出、材料规格），
不是一个总体质量分。

先规则检查（能明确判定的），再语义检查（要读懂文案的）。两类结果分开记：`judge="rule"` 和
`judge="heuristic"|"model"`——两次调用同一个模型仍可能犯相似错误，所以规则判定永远不被模型判断覆盖。

每个问题都包含：出现在哪里、违反哪条条件、对应依据、最小修改、修改后需要重查什么。
检查失败不等于「重写一遍」。

结论的三个取值只对「来源关系」用：找到支持 / 存在矛盾 / 依据不足。其他检查用 pass / fail / undetermined / blocked。
"""
import re
from typing import Any, Callable, Dict, List, Optional

from ..missions import FAMILIES, TASK_VERSION
from ..missions_en import V2_EN
from ..scoring.base import DIM_KEYS
from .blueprints import BLUEPRINTS, CAPABILITIES, OPERATIONS
from .sources import EXCERPTS, PROJECT, RELATIONS, SOURCES, PENDING

SUPPORTED, CONTRADICTS, INSUFFICIENT = "找到支持", "存在矛盾", "依据不足"
PASS, FAIL, UNDET, BLOCKED = "pass", "fail", "undetermined", "blocked"


def _issue(where: str, rule: str, status: str, basis: str = "", min_fix: str = "", recheck: str = "",
           judge: str = "rule", note: str = "", advisory: bool = False) -> Dict[str, Any]:
    """advisory=True 的问题只进报告，不改变候选的整体状态（已知并由用户决定的事、分析时的提醒）。"""
    return dict(where=where, rule=rule, status=status, basis=basis, min_fix=min_fix, recheck=recheck, judge=judge, note=note, advisory=advisory)


# ---------------------------------------------------------------------------
# 规则检查
# ---------------------------------------------------------------------------
_HIDDEN_REQ = re.compile(r"必须(画|用|有|要)|只能用|一定要画")
_FREE_SYMBOL_WORDS = ("图形", "变成什么", "用几块", "哪个概念为主", "画哪一刻", "有谁")


def rule_checks(c: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    tid = c["task_id"]
    bp = BLUEPRINTS.get(c["blueprint"])
    if bp is None and c.get("draft"):
        from .drafts import DRAFT_BLUEPRINTS
        bp = DRAFT_BLUEPRINTS.get(c["blueprint"])
    if bp is None:
        out.append(_issue(tid, "R2 蓝图存在", FAIL, min_fix="补蓝图", recheck="全部"))
        return out
    for k in ("goal", "operation", "inputs", "outputs", "invariants", "band_proposed"):
        if not bp.get(k):
            out.append(_issue(c["blueprint"], f"R2 蓝图六问之「{k}」非空", FAIL, min_fix=f"补 {k}", recheck="候选属性"))
    if bp["operation"] not in OPERATIONS:
        out.append(_issue(c["blueprint"], "R3 操作在索引里", FAIL, min_fix="改成五种操作之一或新增操作定义", recheck="反向提取"))
    # R1 来源关系：每条 excerpt id 存在；项目新增条件必须有 purpose；关系标签合法
    for sr in c["source_relations"]:
        where = f"{tid}: {sr['requirement']}"
        if sr["relation"] not in RELATIONS:
            out.append(_issue(where, "R1 来源关系标签合法", FAIL, min_fix="改成三种关系之一", recheck="本条"))
        if sr["relation"] == PROJECT:
            if not sr.get("purpose"):
                out.append(_issue(where, "R1 项目新增条件必须说用途", FAIL, min_fix="写明这个条件服务什么目标", recheck="本条；是否改变活动目标"))
            continue
        eid = sr.get("excerpt", "")
        ex = EXCERPTS.get(eid)
        if ex is None:
            out.append(_issue(where, "R1 引用的片段存在", FAIL, basis=eid, min_fix="补片段或改成项目新增条件", recheck="本条"))
        elif ex.get("verified") == PENDING or not ex.get("text"):
            out.append(_issue(where, "R1 片段已录入原文", UNDET, basis=f"{eid}（{ex.get('verified')}）",
                              min_fix="录入原文片段后重查", recheck="本条的「找到支持 / 依据不足」"))
    # R4 产出：蓝图说几件、文案要求几件、能力支不支持
    want, by_copy = c["outputs"]["count"], c["outputs"]["required_by_copy"]
    if want != by_copy:
        out.append(_issue(tid, "R4 必要产出数量：蓝图 == 文案", FAIL, basis=f"蓝图 {want} 件，文案要求 {by_copy} 件",
                          min_fix="改文案的产出要求或改蓝图的 outputs.count", recheck="R11 能力；反向提取"))
    if want > 1 and not CAPABILITIES["multi_sketch_output"]:
        out.append(_issue(tid, "R11 产出由现有工具支持", BLOCKED, basis="CAPABILITIES.multi_sketch_output=False",
                          min_fix="先做多草图保存，或把产出改成单幅", recheck="R4"))
    # R5 材料：无参考图必须是明确配置；有参考图的文件要在、规格要在
    mat = c["materials"]
    if mat["kind"] == "none":
        if "note" not in mat:
            out.append(_issue(tid, "R5 「无参考图」是明确配置", FAIL, min_fix="用 materials.NONE", recheck="材料"))
    else:
        if mat.get("spec") is None:
            out.append(_issue(tid, "R5 材料有规格", FAIL, basis=mat.get("id"), min_fix="在 materials.MATERIALS 里补规格", recheck="材料视觉检查"))
        from .materials import file_of
        if mat["kind"] == "reference" and file_of(mat["id"]) is None:
            out.append(_issue(tid, "R5 参考图文件存在", FAIL, basis=mat.get("id"), min_fix="放文件", recheck="材料视觉检查"))
    # R6 新增条件都有用途（上面已查）；R7 文案版本与库一致
    if c["copy"]["version"] != TASK_VERSION and not c.get("draft") and not c.get("bank"):   # 首访库有自己的版本号
        out.append(_issue(tid, "R7 候选对应当前 TASK_VERSION", FAIL, basis=f"{c['copy']['version']} ≠ {TASK_VERSION}", min_fix="重建候选", recheck="全部"))
    # R8 版本与限时
    if not set(c["tiers"]) <= {"simple", "full"} or (not c["tiers"] and not c.get("bank") and not c.get("draft")):   # 首访库按年龄段路由，没有 tier
        out.append(_issue(tid, "R8 tiers 合法", FAIL, min_fix="simple / full", recheck="地图"))
    if c["time_limit_sec"] is not None and not CAPABILITIES["timer"]:
        out.append(_issue(tid, "R8 不限时（2026-10-05 决定）", FAIL, basis=str(c["time_limit_sec"]), min_fix="time_limit_sec=None", recheck="文案里的秒数"))
    # R9 英文文案
    if tid not in V2_EN and not c.get("draft") and not c.get("bank"):
        out.append(_issue(tid, "R9 英文文案存在（missions_en.V2_EN）", FAIL, min_fix="补英文", recheck="test_missions_en"))
    # R10 自由空间 vs 文案：规格说可自主决定的，文案不能悄悄规定
    if any(w in " ".join(c["free"]) for w in _FREE_SYMBOL_WORDS):
        m = _HIDDEN_REQ.search(c["copy"]["instruction"])
        if m:
            out.append(_issue(tid, "R10 文案没有规格之外的硬性规定", FAIL, basis=f"文案含「{m.group(0)}」而规格列为自由空间",
                              min_fix="删掉这条未说明的限制，或把它写成项目新增条件并说用途", recheck="R1；反向提取"))
    # R12 九维关联：维度合法；有理由；可绕开的 secondary 标出来
    for d in c["dims"]:
        if d["dim"] not in DIM_KEYS:
            out.append(_issue(tid, "R12 维度名是 KidsArtBench 九维之一", FAIL, basis=d["dim"], min_fix="改名", recheck="rubric"))
        if d.get("bypass") is None:
            out.append(_issue(tid, "R12 九维关联有理由与成立条件", UNDET, basis=d["dim"], min_fix="在 DIM_NOTES 里补理由", recheck="本条"))
        elif d["bypass"] and d["relation"] == "primary":
            out.append(_issue(tid, "R12 primary 关联不能被合理绕开", FAIL, basis=d["dim"], min_fix="降为 secondary 或改任务条件", recheck="rubric"))
    # R13 文案里的秒数只是引导语（程序不计时）
    if re.search(r"\d+\s*秒", c["copy"]["instruction"]) and not CAPABILITIES["timer"]:
        out.append(_issue(tid, "R13 文案提到秒数而程序不计时", UNDET, basis="phases.seconds 是元数据",
                          min_fix="若用户觉得像限时则删秒数", recheck="文案", note="2026-10-05 已知，留给用户定", advisory=True))
    # R14 工具 vs 文案：文案要求「不擦掉」但橡皮可用 → 由孩子遵守，不由工具保证（记录，不算失败）
    if "不擦掉" in c["copy"]["instruction"] and (c["allowed_tools"] is None or "eraser" in c["allowed_tools"]):
        out.append(_issue(tid, "R14 文案要求由工具保证", UNDET, basis="橡皮可用", min_fix="无需改；分析时用 line_preservation 过程指标核实", recheck="—", advisory=True))
    # R15 内部期望不能成为隐藏要求：家族的过程指标里有 base_form_preservation（还看得出原物）的，
    #     可见文案（题面或提示）里必须有对应的话；否则事后把「看不出原物」当表现不足就是在用隐藏标准
    if "base_form_preservation" in FAMILIES.get(c["family"], {}).get("process_targets", []):
        visible = c["copy"]["instruction"] + c["copy"]["hint"]
        if not re.search(r"看得出|看出|留下|保留|哪些部分|形状能用", visible):
            out.append(_issue(tid, "R15 内部期望（保留原物特征）写进了可见文案", UNDET, basis="题面与提示都没提「留下 / 看得出」",
                              min_fix="在提示里加一句，或分析时不把 base_form_preservation 当该题的要求", recheck="R10"))
    return out


# ---------------------------------------------------------------------------
# 语义检查：反向提取——不给标签，只给文案 + 材料说明 + 产出要求，让判断器说「学生实际要做什么」
# ---------------------------------------------------------------------------
_OP_PATTERNS = [
    # 顺序有讲究：先认「改造 / 设计」（有明确的目标物或用途），再认「片段续画」，再认「照着画」，最后兜底为个人表达
    ("purposeful_design", re.compile(r"把[^。，]+?(改成|改造成|变成)|为[^。]+?设计|从[^。]+?出发，设计|重新设计|设计一[个张]|画一个标志")),
    ("personal_expression", re.compile(r"片段|画进(你的|一幅)画|融入一幅|这些碎片|这些符号|这些线条|这些拼图|接着已有|只改颜色|画里要有|按下面")),
    ("observe_represent", re.compile(r"照着(图|它|原图|眼前)|根据参考图|看参考图|看看图里|画下(桌上|藏宝处|现场|这几样)|把.*画下来|在原(来的)?位")),
    ("personal_expression", re.compile(r"画出|画一|合在一起|合成|画成一幅|接着.*画")),
]


def reverse_extract(copy_text: str, materials: Dict[str, Any]) -> Dict[str, Any]:
    """离线启发式版本的反向提取。可插拔：`semantic_checks(..., judge=fn)` 用模型替换它，但结果仍标 judge 来源。"""
    text = copy_text
    op = None
    for name, pat in _OP_PATTERNS:
        if pat.search(text):
            op = name
            break
    from .candidates import required_outputs
    # 只读文案：文案有没有指向一张图（不看材料配置，否则这项检查就是同义反复）
    uses_ref = bool(re.search(r"照着(图|它|原图|眼前)|看图|图里|图中|参考图|这张图|只剩这张图|剩下这些|剩下的线条|这些碎片|这些符号|这些线条|这些拼图|已有的部分|接着已有|这些东西|这几样|现场的|桌上这", text))
    return dict(operation=op or "personal_expression", outputs=required_outputs(text), uses_reference=uses_ref,
                colour_required=bool(re.search(r"只改颜色|用颜色|颜色、明暗", text)),
                line_only_phase=bool(re.search(r"只用线条", text)),
                constraint_rules=bool(re.search(r"规则|画里要有|按下面", text)))


def semantic_checks(c: Dict[str, Any], judge: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    tid = c["task_id"]
    mode = "model" if judge else "heuristic"
    got = judge(c) if judge else reverse_extract(c["copy"]["instruction"], c["materials"])
    if got.get("operation") and got["operation"] != c["operation"]:
        out.append(_issue(tid, "S1 反向提取的操作 == 声明的操作", CONTRADICTS, basis=f"文案读出 {got['operation']}，声明 {c['operation']}",
                          min_fix="改操作标签，或改文案让它要求声明的操作", recheck="R12 九维关联", judge=mode))
    if got.get("outputs", 1) != c["outputs"]["count"]:
        out.append(_issue(tid, "S2 反向提取的产出数 == 声明产出数", CONTRADICTS, basis=f"文案 {got.get('outputs')} / 声明 {c['outputs']['count']}",
                          min_fix="改文案或改 outputs.count", recheck="R4", judge=mode))
    has_material = c["materials"]["kind"] in ("reference", "fragments")
    if got.get("uses_reference") and not has_material:
        out.append(_issue(tid, "S3 材料用法与文案一致", CONTRADICTS, basis="文案要孩子看图 / 接着碎片画，但材料配置是「无」",
                          min_fix="配上参考图或改文案", recheck="材料", judge=mode))
    elif has_material and c["materials"].get("mode", "always") == "always" and not got.get("uses_reference"):
        out.append(_issue(tid, "S3 文案指向常显的参考图", INSUFFICIENT, basis="参考图常显，但题面没有一句话指向它（孩子要自己猜「这里」是图里）",
                          min_fix="题面加一句「图里的……」；或留着，由提示承担", recheck="—", judge=mode, advisory=True))
    # S4 颜色关联有没有任务条件支持：声明 colour 为 primary 的题，文案必须让目标依赖颜色
    colour_primary = [d for d in c["dims"] if d["dim"].startswith("color") and d["relation"] == "primary"]
    if colour_primary and not got.get("colour_required"):
        out.append(_issue(tid, "S4 Color 为 primary 时文案让目标依赖颜色", CONTRADICTS, basis="文案没有要求用颜色做事",
                          min_fix="降关联或改文案", recheck="R12", judge=mode))
    # S5 可绕开的 secondary：记录为「依据不足」（不是失败），供报告
    for d in c["dims"]:
        if d["relation"] == "secondary" and d.get("bypass"):
            out.append(_issue(tid, "S5 secondary 关联可被合理绕开", INSUFFICIENT, basis=f"{d['dim']}：{d['why']}",
                              min_fix="分析时把它当 exploratory 看；不为保标签强迫学生", recheck="—", judge=mode, advisory=True))
    # S6 来源关系的结论：原文明确规定 / 改编 的条目，片段在且非空 → 找到支持；否则依据不足
    for sr in c["source_relations"]:
        if sr["relation"] == PROJECT:
            continue
        ex = EXCERPTS.get(sr.get("excerpt", ""))
        st = SUPPORTED if (ex and ex.get("text")) else INSUFFICIENT
        out.append(_issue(f"{tid}: {sr['requirement']}", "S6 来源片段支持该要求", st,
                          basis=(sr.get("excerpt") or "") + (f" · {ex['heading']}" if ex else ""),
                          min_fix="" if st == SUPPORTED else "录入片段后由人核一遍是否真的支持", recheck="—", judge="rule"))
    return out


# ---------------------------------------------------------------------------
# 反例：自动制作错误版本，检查检查器本身（不进候选池）
# ---------------------------------------------------------------------------
def mutations(c: Dict[str, Any]) -> List[Dict[str, Any]]:
    import copy as _copy
    out = []
    # 1 把「一幅」改成「两种方案」：产出不一致
    m = _copy.deepcopy(c); m["copy"]["instruction"] += " 画出两种方案。"; m["outputs"]["required_by_copy"] = 2
    out.append(dict(name="outputs_two_schemes", candidate=m, expect=("R4 必要产出数量：蓝图 == 文案",)))
    # 2 在自由设计里插入固定图形要求
    m = _copy.deepcopy(c); m["copy"]["instruction"] += " 必须画一本打开的书。"; m["free"] = list(m["free"]) + ["图形由你决定"]
    out.append(dict(name="hidden_fixed_figure", candidate=m, expect=("R10 文案没有规格之外的硬性规定",)))
    # 3 项目新增条件没有用途
    m = _copy.deepcopy(c); m["source_relations"] = list(m["source_relations"]) + [dict(requirement="必须用三种颜色", relation=PROJECT, excerpt="", purpose="")]
    out.append(dict(name="added_condition_without_purpose", candidate=m, expect=("R1 项目新增条件必须说用途",)))
    # 4 引用一个不存在的片段
    m = _copy.deepcopy(c); m["source_relations"] = list(m["source_relations"]) + [dict(requirement="课标规定三种颜色", relation="原文明确规定", excerpt="kb:p999:nope", purpose="")]
    out.append(dict(name="dangling_excerpt", candidate=m, expect=("R1 引用的片段存在",)))
    # 5 蓝图要两个方案，但能力不支持
    m = _copy.deepcopy(c); m["outputs"]["count"] = 2; m["outputs"]["required_by_copy"] = 2
    out.append(dict(name="multi_output_unsupported", candidate=m, expect=("R11 产出由现有工具支持",)))
    # 6 声明 primary 关联到一个可绕开的维度
    m = _copy.deepcopy(c); m["dims"] = list(m["dims"]) + [dict(dim="color_contrast", relation="primary", why="x", holds_if="—", bypass=True)]
    out.append(dict(name="primary_but_bypassable", candidate=m, expect=("R12 primary 关联不能被合理绕开",)))
    # 7 材料配置：文案说照着图画，却没有参考图（语义检查）
    m = _copy.deepcopy(c); m["copy"]["instruction"] = "照着图把桌上的东西画下来。"; m["materials"] = {"kind": "none", "note": "x"}; m["operation"] = "observe_represent"
    out.append(dict(name="reference_missing_for_copy", candidate=m, expect=("S3 材料用法与文案一致",)))
    return out
