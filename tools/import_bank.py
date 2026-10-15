#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 docs/Task_Library_zh_CN.md + docs/Task_Library_en.md（用户 2026-10-12 给的首访任务库 v1.0.0）
解析成 artquest/bank/first_visit_v1.json——题库读的是这份 JSON，两份 md 是它的来源。

    .venv/bin/python tools/import_bank.py

改题面：改 docs 里的 md，重跑这个脚本，再升 missions_bank.BANK_VERSION。不要手改 JSON。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artquest" / "bank" / "first_visit_v1.json"

BANDS = {"B1": (3, 7), "B2": (8, 10), "B3": (11, 12), "B4": (13, 14), "B5": (15, 16), "B6": (17, 99)}   # B1 从 3 岁起（账号年龄下限）：用户 2026-10-15「6 岁以下也统一五道」，用第一段的题；B6：17 岁及以上（成年初学者也用这个 app）
FAMILY_OF = {"OB": "observe", "ST": "express", "FG": "fragments", "TR": "redesign", "DS": "design"}
ZH_KEYS = {
    "年龄与类型": "age_family", "选题卡摘要": "card", "学生题面（常显）": "prompt", "必要条件（与题面一致）": "requirements",
    "可选提示": "hints", "自由空间": "freedom", "材料与使用": "materials", "学习方向": "intention",
    "复杂度描述（非实测难度）": "complexity", "任务内容分析": "analysis", "不能直接推断": "limits",
    "完成后可选反思": "reflection", "提交和完成后配置": "post_config", "来源定位": "sources", "明确的改编内容": "adaptation",
}
EN_KEYS = {
    "Age and family": "age_family", "Card summary": "card", "Learner prompt (always visible)": "prompt",
    "Requirements (matching the prompt)": "requirements", "On-request hints": "hints", "Creative freedom": "freedom",
    "Materials and use": "materials", "Learning intention": "intention", "Complexity descriptors (not calibrated difficulty)": "complexity",
    "Task-content analysis": "analysis", "Interpretation limits": "limits", "Optional post-task reflection": "reflection",
    "Submission and post-task configuration": "post_config", "Source location": "sources", "Explicit adaptation": "adaptation",
}
ROLE = {"关注": "primary", "探索性": "exploratory", "Focus": "primary", "Exploratory": "exploratory"}


def parse(path: Path, keys, lang: str):
    text = path.read_text("utf-8")
    body = text.split("## 四、逐题完整说明" if lang == "zh" else "## 4. Complete task specifications")[1]
    body = body.split("\n## 五" if lang == "zh" else "\n## 5.")[0]
    out = {}
    for block in re.split(r"\n### ", body)[1:]:
        head, rest = block.split("\n", 1)
        tid, title = [x.strip() for x in head.split("·", 1)]
        fields = {}
        for m in re.finditer(r"\*\*([^*]+)\*\*[：:]\s*(.*?)(?=\n\n\*\*|\n\n---|\Z)", rest, re.S):
            k = m.group(1).strip()
            if k in keys:
                fields[keys[k]] = re.sub(r"\s+", " ", m.group(2).strip())
        dm = re.search(r"\*\*(?:九维关联|Nine-dimensional)[^*]*\*\*\n\n(.*?)(?=\n\n\*\*)", rest, re.S)
        dims = []
        for line in (dm.group(1).splitlines() if dm else []):
            mm = re.match(r"- (\S+) · (.+?) \(`(\w+)`\)[：:]\s*(.*)", line.strip())
            if mm:
                dims.append(dict(key=mm.group(3), role=ROLE[mm.group(1)], label=mm.group(2), why=mm.group(4).strip()))
        hints = []
        for i, h in enumerate(re.split(r"\s*/\s*(?=H\d:)", fields.get("hints", ""))):
            hm = re.match(r"(H\d):\s*(.*)", h.strip())
            if hm:
                hints.append(dict(id=hm.group(1), text=hm.group(2).strip()))
        refs = re.findall(r"assets/([A-Z0-9_]+_ref)\.png", fields.get("materials", ""))
        svg = bool(re.search(r"_ref\.svg", fields.get("materials", "")))
        src_ids = re.findall(r"\[([A-Z0-9]+)\]", fields.get("sources", ""))
        out[tid] = dict(task_id=tid, title=title, fields=fields, dims=dims, hints=hints,
                        reference=refs[0] if refs else None, svg=svg, source_ids=src_ids)
    return out


def main() -> int:
    zh = parse(ROOT / "docs/Task_Library_zh_CN.md", ZH_KEYS, "zh")
    en = parse(ROOT / "docs/Task_Library_en.md", EN_KEYS, "en")
    assert sorted(zh) == sorted(en), (set(zh) ^ set(en))
    tasks = []
    for tid in sorted(zh):          # B1_OB_01 … B5_TR_01：按 id 排，稳定
        z, e = zh[tid], en[tid]
        band, fam, _ = tid.split("_")
        assert [d["key"] for d in z["dims"]] == [d["key"] for d in e["dims"]], tid
        assert [h["id"] for h in z["hints"]] == [h["id"] for h in e["hints"]], tid
        assert z["reference"] == e["reference"], tid
        for f in ZH_KEYS.values():
            assert f in z["fields"], (tid, f)
            assert f in e["fields"], (tid, f)
        tasks.append(dict(
            task_id=tid, band=band, age_min=BANDS[band][0], age_max=BANDS[band][1],
            family=fam, family_slug=FAMILY_OF[fam], order=["OB", "ST", "FG", "TR", "DS"].index(fam),
            reference=z["reference"], reference_svg=z["svg"], source_ids=z["source_ids"],
            dims=[dict(key=d["key"], role=d["role"], why_zh=d["why"], why_en=e["dims"][i]["why"]) for i, d in enumerate(z["dims"])],
            zh=dict(title=z["title"], **{k: v for k, v in z["fields"].items() if k != "hints"}, hints=z["hints"]),
            en=dict(title=e["title"], **{k: v for k, v in e["fields"].items() if k != "hints"}, hints=e["hints"]),
        ))
    doc = dict(bank="first_visit_v1", version="1.0.0", frozen="2026-10-12",
               source_docs=["docs/Task_Library_zh_CN.md", "docs/Task_Library_en.md", "docs/Student_Tasks_CN_EN.md"],
               bands=[dict(id=b, age_min=lo, age_max=hi) for b, (lo, hi) in BANDS.items()],
               families=FAMILY_OF, post_config="first_visit_common_v1", tasks=tasks)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(tasks)} tasks, {sum(1 for t in tasks if t['reference'])} with reference")
    return 0


if __name__ == "__main__":
    sys.exit(main())
