# -*- coding: utf-8 -*-
"""首访任务库 v1.0.0（用户 2026-10-12 给的 docs/Task_Library_zh_CN.md / Task_Library_en.md / Student_Tasks_CN_EN.md）。

25 道、按年龄五段（6–7 / 8–10 / 11–12 / 13–14 / 15–16）路由，每段固定五道（观察 / 表达 / 图形片段 / 物品改造 / 视觉设计），
一次只做一道。它替换的是**第一次来**看到的那一屏，不是对 M1–M9 的重建；M 族照旧留在库里。

数据在 `artquest/bank/first_visit_v1.json`（由 `tools/import_bank.py` 从两份 md 生成，不手改）。这里只把它变成和 M 族同形的行：

    tiers = []                  不进简单版 / 完整版那套抽题；靠 band 路由
    bank = "first_visit_v1"     前端据此认出它
    hints = [{id, text}, …]     按需显示的固定提示（不是必要条件）；显示时记 HINT_SHOW 事件
    requirements                必要条件，和题面一致，学生看得见
    reflection                  完成后可跳过的反思问题
    condition.revision_enabled = False   首访默认不开修改轮
    stimulus.fit = "contain"    参考图完整显示，不裁

共用的完成后配置 `first_visit_common_v1`：保存一幅首稿；喜欢程度 / 感觉难度 / 反思各可跳过；不因反馈未到而阻止结束。
"""
import json
from pathlib import Path
from typing import Any, Dict, List

BANK = "first_visit_v1"
BANK_VERSION = "1.0.1"          # 1.0.0 冻结 2026-10-12；1.0.1 同日：B2/B3/B4 观察题按图改对象名。改题面 → 改 docs → 重跑 import_bank → 升这里
POST_CONFIG = "first_visit_common_v1"
DATA = Path(__file__).resolve().parent / "bank" / "first_visit_v1.json"

_DOC: Dict[str, Any] = json.loads(DATA.read_text("utf-8"))
REFS_DIR = Path(__file__).resolve().parents[1] / "static" / "refs" / "bank"


def _ref_size(sid: str) -> List[int]:
    """参考图的原生像素。2026-10-12 用户给的图不是 1600×1200（插画版是从展示拼版精确裁出的 295–443 px），
    文档的规格数字不作依据；记实际尺寸，显示用 contain，不放大不裁切。"""
    try:
        from PIL import Image
        with Image.open(REFS_DIR / f"{sid}.png") as im:
            return list(im.size)
    except Exception:
        return []
BANDS: List[Dict[str, Any]] = list(_DOC["bands"])
ORDER = ["OB", "ST", "FG", "TR", "DS"]

# 五个家族（评分契约：家族层面不声明维度，primary 由每道题自己带；其余 exploratory）
BANK_FAMILIES: Dict[str, Dict[str, Any]] = {
    "OB": dict(slug="observe", name="观察与表现", icon="👀", color="#4db8ef", difficulty=2,
               research_goal="首访：观察与表现（共同参考允许比较外形与关系）", time_limit_sec=None, allowed_tools=None,
               prompt_style="plain", rubric={}, bank=BANK,
               process_targets=["reference_viewing", "canvas_reference_switch", "layout_establishment_time", "proportion_revision"]),
    "ST": dict(slug="express", name="个人表达与叙事", icon="💬", color="#3fae8a", difficulty=2,
               research_goal="首访：个人表达与叙事（单幅、不写故事）", time_limit_sec=None, allowed_tools=None,
               prompt_style="plain", rubric={}, bank=BANK,
               process_targets=["planning_latency", "new_element_count", "region_switching"]),
    "FG": dict(slug="fragments", name="图形片段创作", icon="🧩", color="#b98cf0", difficulty=2,
               research_goal="首访：从参考区的原创图形片段发展一幅画（参考 Urban 2005 p.273 的范式；片段转抄不印在画布上）",
               time_limit_sec=None, allowed_tools=None, prompt_style="plain", rubric={}, bank=BANK,
               process_targets=["planning_latency", "first_fragment_used", "fragment_integration_order", "idea_shift"]),
    "TR": dict(slug="redesign", name="物品创意改造", icon="🔧", color="#f2706e", difficulty=2,
               research_goal="首访：把一件参考物品改造成新用途，保留可辨认特征", time_limit_sec=None, allowed_tools=None,
               prompt_style="plain", rubric={}, bank=BANK,
               process_targets=["first_transformation_time", "base_form_preservation", "semantic_shift"]),
    "DS": dict(slug="design", name="视觉传达设计", icon="🪧", color="#f5c243", difficulty=2,
               research_goal="首访：为一个明确用途做一张标志 / 吉祥物 / 海报", time_limit_sec=None, allowed_tools=None,
               prompt_style="plain", rubric={}, bank=BANK,
               process_targets=["planning_latency", "new_element_count", "large_revision"]),
}


def band_of(age: Any) -> Dict[str, Any]:
    """年龄 → 段；范围外或没给 → {}（不静默分配）。"""
    try:
        a = int(age)
    except (TypeError, ValueError):
        return {}
    for b in BANDS:
        if b["age_min"] <= a <= b["age_max"]:
            return dict(b)
    return {}


def tasks() -> List[Dict[str, Any]]:
    return sorted(_DOC["tasks"], key=lambda t: (t["band"], t["order"]))


def build_bank(row_fn, families: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """`row_fn` 是 missions._row；这里不 import 它，避免循环。"""
    out = []
    for t in tasks():
        fam, zh, en = t["family"], t["zh"], t["en"]
        stim = None
        if t["reference"]:
            sid = t["reference"]            # B1_OB_ref
            stim = {"kind": "reference", "stimulus_id": sid, "id": sid, "file": f"/static/refs/bank/{sid}.png",
                    "mode": "always", "fit": "contain", "size": _ref_size(sid), "svg": False}   # 没有可编辑 SVG（v3 包说明）
        cond = dict(bank=BANK, bank_version=BANK_VERSION, band=t["band"], age_min=t["age_min"], age_max=t["age_max"],
                    post_config=POST_CONFIG, revision_enabled=False, reference_fit="contain",
                    hint_ids=[h["id"] for h in zh["hints"]])
        row = row_fn(fam, t["task_id"], title=zh["title"], instruction=zh["prompt"], hint="",
                     stimulus=stim, condition=cond, version=BANK_VERSION, tiers=[], anchor=False, legacy=False)
        row["task_id"] = row["id"] = t["task_id"]          # 不要 _row 拼出来的 OB_B1_OB_01
        row["form_id"] = t["task_id"]
        row["rubric"] = {"primary_dimensions": [d["key"] for d in t["dims"] if d["role"] == "primary"]}
        row["dim_notes"] = [dict(key=d["key"], role=d["role"], why=d["why_zh"]) for d in t["dims"]]
        row.update(bank=BANK, band=t["band"], age_min=t["age_min"], age_max=t["age_max"], order=t["order"],
                   card=zh["card"], requirements=zh["requirements"], hints=list(zh["hints"]), reflection=zh["reflection"],
                   post_config=POST_CONFIG, source_ids=list(t["source_ids"]),
                   i18n_en=dict(title=en["title"], instruction=en["prompt"], card=en["card"], requirements=en["requirements"],
                                hints=list(en["hints"]), reflection=en["reflection"], hint=""))
        out.append(row)
    return out
