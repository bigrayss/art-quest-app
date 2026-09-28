# -*- coding: utf-8 -*-
"""生成 `docs/TASK_LIST.md` —— 全部 75 个任务，给老师逐条看、逐条提意见。

结构和文字都从代码里抽（`artquest/missions.py` 是唯一的原文），所以老师改了意见、
我改了代码、重跑一次，清单就和 app 里孩子看到的一字不差。

    python3 tools/gen_task_list.py            # 写进 docs/TASK_LIST.md
    python3 tools/gen_task_list.py --stdout
"""
import os
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ARTQUEST_SCORER", "heuristic")
os.environ.setdefault("ARTQUEST_FEEDBACK", "template")

from artquest.quests import QUESTS, families  # noqa: E402
from artquest.scoring import DIMENSIONS  # noqa: E402
from artquest import missions as _m  # noqa: E402

# 变体里的英文键 → 孩子看到的中文（M4 的物品/环境/目标、M5 的两个概念、M7 的概念）
_WORD = {}
for tbl in (getattr(_m, "M4_BASE", []), getattr(_m, "M4_ENV", []), getattr(_m, "M4_GOAL", [])):
    for row in tbl:
        _WORD[row[0]] = row[-1]
for row in getattr(_m, "M5_PAIRS", []):
    _WORD[row[0]] = row[2]
    _WORD[row[1]] = row[3]
for row in getattr(_m, "M7_CONCEPTS", []):
    _WORD[row[0]] = row[1]
_KEY_ZH = {"base_object": "物品", "environment": "环境", "goal": "目标", "concept_a": "概念一", "concept_b": "概念二",
           "concept": "概念", "rules": "规则", "narrative_card": "叙事提示", "mood": "心情", "when": "时间"}

ZH = {d["key"]: d["zh"] for d in DIMENSIONS}
TOOL_ZH = {"pencil": "铅笔", "brush": "画笔", "marker": "马克笔", "eraser": "橡皮", "undo": "撤销", "redo": "重做", "zoom": "缩放"}
STYLE_ZH = {"minimal": "极简版", "story": "故事版", "challenge": "挑战版"}
FAMILY_NOTE = {
    "M0": "最早的五个开放任务，没有时限、不限工具。它们是 app 的「自由创作」那块地。",
    "M1": "看一张损坏的参考图，把场景重新画出来。看的是整体结构与位置关系，不是画得像不像。四张是平行卷。",
    "M2": "看一张静物参考图（正好 4 个物体、2 处遮挡），画出谁在前、谁被挡、谁更大。四张是平行卷。",
    "M3": "画布上印着几块程序生成的碎片（不是图片），孩子把它们补成一幅画。每题另附一句叙事提示。",
    "M4": "把一件日常物品改造成另一样东西。同一组「物品 × 环境 × 目标」有三种说法：极简 / 故事 / 挑战，考的是提示语措辞对创作的影响。参考图默认收起，点一下才看。",
    "M5": "把两个毫不相干的东西融合成一个新生物。和 M4 的区别：M4 改造一件，M5 融合两件。",
    "M6": "看一张情绪中性的场景参考图，用颜色把它改成某种心情 / 天气 / 时间。考的是颜色的表达。",
    "M7": "两步：第一步 60 秒只用铅笔画线条表现一个概念（不许画具体东西）；第二步不许删掉，把这些线发展成一幅画。",
    "M8": "给两条「世界规则」，画出规则成立的世界里的生活。最接近真实的自由创作，但由规则约束。",
    "M9": "开放的故事题，没有参考图。用来看受控任务里的行为模式在真实创作里还在不在。",
}


def cond_zh(c):
    """条件里的变体，用中文说：优先取 *_zh 字段。"""
    if not c:
        return ""
    out = []
    used = set()
    for k, v in c.items():
        if k.endswith("_zh"):
            base = k[:-3]
            out.append(f"{base}={v}")
            used.add(base)
    for k, v in c.items():
        if k.endswith("_zh") or k in used or k in ("two_phase", "rule_refs", "fragment_seed"):
            continue
        if isinstance(v, list):
            v = "；".join(map(str, v))
        out.append(f"{_KEY_ZH.get(k, k)}={_WORD.get(v, v)}")
    return " · ".join(f"{_KEY_ZH.get(x.split('=')[0], x.split('=')[0])}={x.split('=', 1)[1]}" for x in out)


def dims(q, key):
    return "、".join(ZH.get(k, k) for k in (q.get("rubric") or {}).get(key, []))


def main() -> int:
    by_fam = OrderedDict()
    for q in QUESTS:
        by_fam.setdefault(q["family"], []).append(q)
    fams = {f["id"]: f for f in families()}

    L = []
    w = L.append
    w("# 任务清单（给老师看的版本）\n")
    w(f"app 里孩子能抽到的全部 **{len(QUESTS)} 个任务**，按 10 个家族分。每个任务写了孩子看到的原话、提示、参考图、时限、"
      "工具限制和它主要考察的维度。**编号可以直接拿来指**：`4.7` 就是第 4 家族第 7 个任务。\n")
    w("> 由 `tools/gen_task_list.py` 从代码里生成，文字和 app 里的一字不差。**别手改这个文件**——"
      "意见写在别处（邮件、批注、或者直接写在最后一列复制走），我改进代码后重跑一次它就更新。\n")
    w("## 怎么提意见\n")
    w("对着编号说就行，比如「4.7 的指令改成……」「2.3 的提示太抽象」「M6 时限太短」。能改的东西：\n")
    w("- **标题、指令原话、提示语**：想怎么说就写出来，我照抄进去。\n"
      "- **时限、允许的工具、参考图开不开**：家族级的设置，说清楚哪个家族。\n"
      "- **一个任务主要考察哪几个维度**：见每节的「主要考察」。九个维度**每幅画都评**，「主要考察」只是说这个任务额外想看的。\n"
      "- **增删任务、换参考图的内容**：也可以，写清楚要什么。\n")
    w("有两样请先商量再改：任务的 **id**（它是所有数据表的外键，改了历史数据就对不上）；"
      "M3 的碎片（程序生成的，前后端要逐像素对上，不能换成图片）。\n")
    w("## 九个维度\n")
    w("| 维度 | 看的是什么 |")
    w("| --- | --- |")
    for d in DIMENSIONS:
        w(f"| **{d['zh']}** | {d['desc']} |")
    w("\n---\n")

    n_fam = 0
    for fid, rows in by_fam.items():
        n_fam += 1
        f = fams.get(fid, {})
        first = rows[0]
        w(f"## {n_fam}. {fid} {f.get('name', first.get('family_name', ''))} · {len(rows)} 题\n")
        w(FAMILY_NOTE.get(fid, "") + "\n")
        limits = sorted({q.get("time_limit_sec") for q in rows}, key=lambda x: (x is None, x))
        tools = sorted({tuple(q.get("allowed_tools") or []) for q in rows})
        stim = {(q.get("stimulus") or {}).get("kind", "none") for q in rows}
        stim_zh = {"none": "无", "reference": "参考图", "fragments": "画布上的碎片"}
        w("| 项 | 设置 |")
        w("| --- | --- |")
        w(f"| 难度 | {f.get('difficulty', first.get('difficulty'))} / 5 |")
        w("| 时限 | " + " / ".join("不限时" if t is None else f"{t // 60} 分钟" for t in limits) + " |")
        w("| 工具 | " + " / ".join("不限" if not t else "、".join(TOOL_ZH.get(x, x) for x in t) for t in tools) + " |")
        w("| 参考图 | " + "、".join(stim_zh.get(s, s) for s in sorted(stim))
          + ("（默认收起，点一下才看）" if any((q.get("stimulus") or {}).get("mode") == "on_demand" for q in rows) else "") + " |")
        sec = dims(first, 'secondary_dimensions')
        w(f"| 主要考察 | **{dims(first, 'primary_dimensions')}**" + (f"；其次 {sec}" if sec else "") + " |")
        w(f"| 研究目的 | {f.get('research_goal', first.get('research_goal', ''))} |")
        if first.get("phases"):
            steps = "；".join(f"第 {i + 1} 步「{p['label']}」" + (f" {p['seconds']} 秒" if p.get("seconds") else "")
                             + (f"，只能用 {'、'.join(TOOL_ZH.get(t, t) for t in p['allowed_tools'])}" if p.get("allowed_tools") else "")
                             for i, p in enumerate(first["phases"]))
            w(f"| 分步 | {steps} |")
        w("")
        w("| 编号 | id | 标题 | 孩子看到的指令 | 提示 | 变体 | 老师意见 |")
        w("| --- | --- | --- | --- | --- | --- | --- |")
        for i, q in enumerate(rows, 1):
            instr = (q.get("instruction") or "").replace("\n\n", " ⏎ ").replace("\n", " ⏎ ").replace("|", "／")
            hint = (q.get("hint") or "").replace("|", "／")
            variant = []
            if fid == "M4" and q.get("prompt_style") in STYLE_ZH:     # 只有 M4 的三种说法是实验变量
                variant.append(STYLE_ZH[q["prompt_style"]])
            c = cond_zh(q.get("condition"))
            if c:
                variant.append(c)
            ref = (q.get("stimulus") or {})
            if ref.get("kind") == "reference":
                variant.append(f"参考图 `{ref.get('stimulus_id')}`")
            w(f"| {n_fam}.{i} | `{q['id']}` | {q.get('title', '')} | {instr} | {hint} | {' · '.join(variant)} |  |")
        w("\n---\n")

    out = "\n".join(L) + "\n"
    if "--stdout" in sys.argv:
        sys.stdout.write(out)
    else:
        (ROOT / "docs/TASK_LIST.md").write_text(out, encoding="utf-8")
        print(f"wrote docs/TASK_LIST.md: {len(QUESTS)} tasks in {n_fam} families")
    return 0


if __name__ == "__main__":
    sys.exit(main())
