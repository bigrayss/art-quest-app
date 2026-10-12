# -*- coding: utf-8 -*-
"""把任务空间写成人能读的报告（markdown）和 Agent 能读的 JSON。生成物放 docs/任务空间/，不要手改。"""
import json
from pathlib import Path
from typing import Any, Dict, List

from .blueprints import OPERATIONS
from .materials import render_frames
from .sources import CONTENT, PENDING
from .space import initialize

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "任务空间"


def _md_table(head: List[str], rows: List[List[Any]]) -> str:
    lines = ["| " + " | ".join(head) + " |", "| " + " | ".join("---" for _ in head) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ") for x in r) + " |")
    return "\n".join(lines)


def _sources_md(ts: Dict[str, Any]) -> str:
    rows = []
    for sid, s in ts["sources"].items():
        n = [e for e in ts["excerpts"].values() if e["source"] == sid]
        ok = sum(1 for e in n if e["verified"] != PENDING and e["text"])
        rows.append([sid, s["name"], "内容" if s["kind"] == CONTENT else "方法", s["role"], f"{ok}/{len(n)}", s.get("file_note", "")])
    ex_rows = [[e["id"], e.get("band", ""), e["heading"], (e.get("page_body") if e.get("page_body") is not None else "—"), (e.get("page_pdf") if e.get("page_pdf") is not None else "—"),
                e["verified"], e["requirement"]] for e in ts["excerpts"].values()]
    return ("## 1. 来源\n\n内容来源解释「为什么设计这种美术活动」，方法来源解释「怎样把资料转成可检查的任务」；两套记录不混写。\n\n"
            + _md_table(["id", "资料", "类", "作用", "已录入片段", "文件说明"], rows)
            + "\n\n### 1.1 片段（正文页与 PDF 页分开记；`待录入` = 没拿到原文，不按记忆补）\n\n"
            + _md_table(["片段 id", "学段", "位置", "正文页", "PDF 页", "核对", "原始要求"], ex_rows)
            + "\n\n原文见 `artquest/taskspace/sources.py`（检查设计依据时读的是原文，不是这里的摘要）。\n")


def _blueprints_md(ts: Dict[str, Any]) -> str:
    parts = ["## 2. 蓝图（任务规格，不是主题列表）\n"]
    for bid, bp in ts["blueprints"].items():
        parts.append(f"### {bid} · {bp['title']}\n")
        parts.append(_md_table(["问题", "回答"], [
            ["适用学段", f"来源：{'、'.join(bp['band_source']) or '—'}；拟适用：simple = {bp['band_proposed'].get('simple')}；full = {bp['band_proposed'].get('full')}"],
            ["学习目标", bp["goal"]],
            ["操作", f"{bp['operation']}（{OPERATIONS.get(bp['operation'], '')}）；内容属性：{', '.join(bp['content']) or '—'}"],
            ["必须提供的输入", "；".join(f"{k}: {v}" for k, v in bp["inputs"].items())],
            ["必须保留的产出", f"{bp['outputs']['count']} 件 · {bp['outputs']['form']}"],
            ["不能改的条件", "；".join(bp["invariants"])],
            ["自由空间", "；".join(bp["free"])],
            ["负担组成", "；".join(f"{k}={v}" for k, v in bp["load"].items())],
        ]))
        parts.append("\n来源关系：\n")
        parts.append(_md_table(["设计要求", "关系", "片段", "用途（新增条件）"],
                               [[r["requirement"], r["relation"], r.get("excerpt", "") or "—", r.get("purpose", "") or "—"] for r in bp["source_relations"]]))
        parts.append("")
    # 覆盖：学段 × 操作
    parts.append("### 2.x 覆盖与缺口\n")
    bands = ["一(1–2)", "二(3–5)", "三(6–7)", "四(8–9)"]
    rows = []
    for op in OPERATIONS:
        row = [op]
        for b in bands:
            hits = [bid for bid, bp in ts["blueprints"].items() if bp["operation"] == op and b in bp["band_source"]]
            row.append(", ".join(hits) or "—")
        rows.append(row)
    parts.append(_md_table(["操作 \\ 来源学段"] + bands, rows))
    parts.append("\n课标里有、本库没有蓝图的（保留缺口比用相似题填满更有用）：\n")
    parts.append(_md_table(["操作", "依据片段", "为什么没有", "需要的能力", "备注"],
                           [[g["operation"], ", ".join(g["excerpts"]), g["why_missing"], ", ".join(g["needs"]) or "现有能力已够", g["note"]] for g in ts["gaps"]]))
    return "\n".join(parts) + "\n"


def _candidates_md(ts: Dict[str, Any]) -> str:
    parts = ["## 3. 候选（库里 80 道 v2 题，每道都回到蓝图）\n",
             "状态：`clear` = 规定范围内没发现未解决的一致性问题（**不是已校准**）；`open` = 有无法判断 / 依据不足的项；`blocked` = 有明确矛盾。\n"]
    by_fam: Dict[str, List[Dict[str, Any]]] = {}
    for c in ts["candidates"]:
        by_fam.setdefault(c["family"], []).append(c)
    for fam, cs in by_fam.items():
        parts.append(f"### {fam} → {cs[0]['blueprint']}\n")
        rows = []
        for c in cs:
            dims = ", ".join(f"{d['dim']}{'*' if d.get('bypass') else ''}" for d in c["dims"])
            mat = c["materials"]
            mat_s = "无参考图（明确配置）" if mat["kind"] == "none" else f"{mat['id']}（{mat.get('mode', mat['kind'])}）→ {c.get('material_check', '')}"
            open_issues = [i for i in c["issues"] if not i.get("advisory") and i["status"] not in ("pass", "找到支持")]
            demoted = ", ".join(f"{d}→exploratory" for d in c.get("demoted", {})) or "—"
            rows.append([c["task_id"], "/".join(c["tiers"]) + ("·锚" if c["anchor"] else ""), c["copy"]["title"],
                         "；".join(x for x in c["variation"]["changed"]) or "锚定题", dims, demoted, mat_s, c["status"],
                         "；".join(f"{i['rule']}（{i['basis']}）" for i in open_issues) or "—"])
        parts.append(_md_table(["task_id", "版本", "题", "相对锚定题改变了", "九维关联（* = 可合理绕开）", "实例级降级（2026-10-11）", "材料 → 检查", "状态", "未决问题"], rows))
        parts.append("")
    return "\n".join(parts) + "\n"


def _drafts_md(ts: Dict[str, Any]) -> str:
    d = ts["drafts"]
    parts = ["## 3.x 草案（2026-10-11 先补的两类；**没有进库**，没有 task_id 和评分契约）\n"]
    for bid, bp in d["blueprints"].items():
        parts.append(f"**{bid} · {bp['title']}** — {bp['goal']}；操作 {bp['operation']}；来源：" +
                     "；".join(f"{r['requirement']}（{r['relation']}{'，' + r['excerpt'] if r.get('excerpt') else ''}）" for r in bp["source_relations"]) + "\n")
    rows = []
    for c in d["candidates"]:
        open_issues = [i for i in c["issues"] if not i.get("advisory") and i["status"] not in ("pass", "找到支持")]
        mat = c["materials"]
        rows.append([c["task_id"], c["blueprint"], c["copy"]["title"], c["copy"]["instruction"],
                     "无参考图（明确配置）" if mat["kind"] == "none" else f"{mat['id']}（{mat['spec'].get('status', '')}）",
                     ", ".join(f"{x['dim']}({x['relation']})" for x in c["dims"]), c["status"],
                     "；".join(f"{i['rule']}（{i['basis']}）" for i in open_issues) or "—"])
    parts.append(_md_table(["草案 id", "蓝图", "题", "文案", "材料", "九维关联", "状态", "未决问题"], rows))
    return "\n".join(parts) + "\n"


def _materials_md(ts: Dict[str, Any]) -> str:
    parts = ["## 4. 材料检查（按依赖；没有视觉模型时需要看图的项是「无法判断」，裁出的显示帧在 `frames/`）\n"]
    rows = []
    for sid, r in ts["materials"].items():
        measured = r.get("measured") or {}
        if "spec" not in r:
            rows.append([sid, "（草案材料，还没制作）", "—", "—", r["status"], "；".join(i["note"] for i in r["items"]), "—"])
            continue
        failing = [i["note"] for i in r["items"] if i["status"] == "不符合"]
        unknown = sum(1 for i in r["items"] if i["status"] == "无法判断")
        blocked = sum(1 for i in r["items"] if i["status"] == "阻塞")
        rows.append([sid, r["spec"]["purpose"], r["spec"]["presentation"],
                     f"sat={measured.get('saturation', '—')} fill_h={measured.get('fill_height', '—')}" if measured else "矢量",
                     r["status"], "；".join(failing) or "—", f"{unknown} 项待看图 / {blocked} 项被前提阻塞"])
    parts.append(_md_table(["材料", "用途", "呈现类型", "量到的", "结论", "不符合的项", "视觉项"], rows))
    parts.append("\n每份材料的问题清单（对象 → 可辨识 → 关系 → 显示帧）在 JSON 的 `materials[*].items` 里。\n")
    return "\n".join(parts) + "\n"


def _advisories_md(ts: Dict[str, Any]) -> str:
    rows = []
    seen = set()
    for c in ts["candidates"]:
        for i in c["issues"]:
            if i.get("advisory"):
                key = (i["rule"], i["basis"])
                if key in seen:
                    continue
                seen.add(key)
                rows.append([i["rule"], i["basis"], i["min_fix"], c["family"]])
    return "## 5. 提醒（不改变状态，分析时要记得）\n\n" + _md_table(["检查", "依据", "怎么处理", "首见家族"], rows) + "\n"


def write(out_dir: Path = OUT) -> Dict[str, Any]:
    ts = initialize()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "taskspace.json").write_text(json.dumps(ts, ensure_ascii=False, indent=1, default=str), "utf-8")
    render_frames(out_dir / "frames")
    s = ts["summary"]
    head = (f"# 任务空间（Phase 0 任务初始化）· 任务库 v{ts['task_version']}\n\n"
            f"> 由 `tools/taskspace_report.py` 生成，**别手改**；改 `artquest/taskspace/*.py` 再重跑。\n\n"
            f"候选 {s['candidates']} 道：clear {s['status']['clear']} · open {s['status']['open']} · blocked {s['status']['blocked']}。\n\n"
            "现有产品能力（任务要求的操作必须由工具 + 材料共同支持）：\n\n"
            + _md_table(["能力", "有没有"], [[k, "有" if v else "**没有**"] for k, v in ts["capabilities"].items()]) + "\n\n")
    body = (head + _sources_md(ts) + "\n" + _blueprints_md(ts) + "\n" + _candidates_md(ts) + "\n" + _drafts_md(ts) + "\n"
            + _materials_md(ts) + "\n" + _advisories_md(ts))
    (out_dir / "README.md").write_text(body, "utf-8")
    return ts
