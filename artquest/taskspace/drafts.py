# -*- coding: utf-8 -*-
"""草案：课标里有、库里没有、现有能力够做的两类任务（2026-10-11 用户定的「先补两类」）。

这里的蓝图和候选**没有进 missions_v2**——没有 task_id、不上地图、没有评分契约（FAMILIES）；
它们走同一套检查，报告里单列「草案」。要进库得走加题的规矩（FAMILIES 一条 + missions_v2 + V2_EN + 升 TASK_VERSION）。
每条蓝图先给两个候选，用来比较变化是否受控（同操作、不同情境），不是为了凑数。
"""
from typing import Any, Dict, List

from .blueprints import _req
from .materials import NONE
from .sources import ADAPTED, PROJECT, VERBATIM

DRAFT_BLUEPRINTS: Dict[str, Dict[str, Any]] = {
    "BP_D1": dict(
        family="D1", title="为校园里一个明确用途设计一个标志（草案）", draft=True,
        band_source=["一(1–2)", "二(3–5)"], band_proposed={"simple": "小学（课标第二学段：为班级或学校的活动设计标识）", "full": "拟适用初中：同一操作，题面只需换措辞；第三学段有「根据活动需要设计海报、请柬」"},
        goal="在校园情境中，为一个明确用途设计一个图形标志，让看到的人知道这里 / 这件事是什么",
        operation="purposeful_design", content=["composition"],
        inputs=dict(reference="无参考图（明确配置）", canvas="空白"),
        outputs=dict(count=1, form="单幅标志设计"),
        invariants=["回应一个明确用途（用途由题给定）", "单幅产出", "没有示范图"],
        free=["图形", "颜色", "是否有文字", "风格"],
        load=dict(compare_schemes=0, spatial_relations=False, read_text=False, modify_existing=False),
        source_relations=[
            _req("为班级或学校的活动设计标识、请柬、贺卡、图表、海报", VERBATIM, "kb:p56:t3-visual-design"),
            _req("利用画笔或计算机为自己 / 同学做小设计（名片、席卡）", VERBATIM, "kb:p52:t5-design"),
            _req("识别公共场所的标识，了解其用途和所传递的信息", VERBATIM, "kb:p49:t1-signs"),
            _req("数字画布 + 只提交一份设计", ADAPTED, "kb:p56:t3-visual-design"),
            _req("具体场所（图书角 / 运动用品区）由项目给定", PROJECT, purpose="让「回应一个明确用途」有落点；场所是变式参数，不改操作"),
        ]),
    "BP_D2": dict(
        family="D2", title="看着一样自然的东西，把它的形状、颜色和纹理画下来（草案）", draft=True,
        band_source=["一(1–2)", "二(3–5)"], band_proposed={"simple": "小学（第一学段：观赏自然对象，感知其形状美、色彩美、肌理美）", "full": "拟适用初中：同一操作，参考图换成结构更复杂的对象（树皮、贝壳的螺旋）"},
        goal="观察一个自然对象的形状、颜色与纹理并表现出来（和 M1/M2 的人造场景拉开）",
        operation="observe_represent", content=["line", "color"],
        inputs=dict(reference="单个自然对象的特写参考图（叶子 / 贝壳 / 树皮 / 羽毛），mode=always", canvas="空白"),
        outputs=dict(count=1, form="单幅观察画"),
        invariants=["参考图常显", "对象是自然物、一张图一个对象", "要求画出形状 + 颜色 + 纹理三样", "单幅产出"],
        free=["画多大", "背景", "工具"],
        load=dict(compare_schemes=0, spatial_relations=False, read_text=False, modify_existing=False),
        source_relations=[
            _req("观赏自然环境中的山水、树木、花草、动物，感知其形状美、色彩美和肌理美", VERBATIM, "kb:p49:t1-nature"),
            _req("课标承认「临摹」是模仿与改变原作的手法之一（教学提示谈的是与抄袭的区别）", ADAPTED, "kb:p58:copy-vs-change", support="间接"),
            _req("观察对象改为一张特写参考图而不是实物", ADAPTED, "kb:p49:t1-nature"),
            _req("一张图只放一个对象、无背景干扰", PROJECT, purpose="把观察集中在形状 / 颜色 / 纹理，不混入空间关系（那是 M2 的事）"),
        ]),
}

# 材料规格（参考图还没制作：文件不存在会被 R5 拦住，这是如实的状态）
DRAFT_MATERIALS: Dict[str, Dict[str, Any]] = {
    "d2_nature_a": dict(id="d2_nature_a", kind="reference", purpose="正式观察参考（D2：形状 / 颜色 / 纹理）",
                        objects=["一片叶子（有清楚的叶脉）"], relations=["占画面高约 70 %", "素色背景", "叶脉纹理在缩略图里仍可见"],
                        presentation="照片或写实插画（和 M1/M2 不是一套也没关系：这是单对象特写）", must_not=["文字", "商标", "第二个对象"],
                        variable=["叶子的种类", "颜色"], status="待制作"),
    "d2_nature_b": dict(id="d2_nature_b", kind="reference", purpose="正式观察参考（D2）",
                        objects=["一只贝壳（有螺旋或条纹）"], relations=["占画面高约 70 %", "素色背景", "纹理在缩略图里仍可见"],
                        presentation="照片或写实插画", must_not=["文字", "商标", "第二个对象"], variable=["贝壳的种类", "颜色"], status="待制作"),
}


def _cand(code: str, bp: str, tiers: List[str], title: str, text: str, hint: str, materials: Dict[str, Any],
          dims: List[Dict[str, Any]], added: List[Dict[str, str]], changed: List[str]) -> Dict[str, Any]:
    from .blueprints import BLUEPRINTS  # noqa: F401  (保持导入顺序一致)
    b = DRAFT_BLUEPRINTS[bp]
    import hashlib
    return dict(
        task_id=f"{b['family']}_{code}", family=b["family"], blueprint=bp, tiers=tiers, anchor=len(tiers) == 2, draft=True,
        copy=dict(title=title, instruction=text, hint=hint, version="draft", sha=hashlib.sha1(text.encode()).hexdigest()[:12]),
        operation=b["operation"], content=list(b["content"]),
        outputs=dict(count=1, form=b["outputs"]["form"], required_by_copy=1),
        inputs=dict(b["inputs"]), fixed=list(b["invariants"]) + [a["requirement"] for a in added], free=list(b["free"]),
        load=dict(b["load"]), source_relations=list(b["source_relations"]) + added, dims=dims, materials=materials,
        condition={}, allowed_tools=None, time_limit_sec=None, phases=None,
        variation=dict(against=None if not changed else f"{b['family']}_A1", changed=changed, kept=["操作", "产出数量", "工具"] if changed else ["（锚定题本身）"]),
        demoted={},
    )


def build_draft_candidates() -> List[Dict[str, Any]]:
    d1_dims = [dict(dim="picture_organization", relation="primary", why="要把视觉元素组织成一个能被认出的整体", holds_if="文案要求「一个标志」", bypass=False),
               dict(dim="imagination", relation="secondary", why="图形构想的新颖程度", holds_if="—", bypass=False)]
    d2_dims = [dict(dim="realism", relation="primary", why="形状、颜色、纹理要画得像", holds_if="参考图常显且文案要求三样", bypass=False),
               dict(dim="line_texture", relation="primary", why="纹理靠线条的肌理表现", holds_if="文案要求画出纹理", bypass=False),
               dict(dim="color_richness", relation="secondary", why="文案要求画出颜色；颜色层次可观察", holds_if="文案要求画出颜色", bypass=False)]
    return [
        _cand("A1", "BP_D1", ["simple", "full"], "图书角标志",
              "为班级图书角设计一个标志，让同学看到它就想到这里可以阅读。图形和颜色由你决定。",
              "想想「可以阅读」怎么用一个图形说出来。", dict(NONE), d1_dims,
              [dict(requirement="场所：图书角", relation=PROJECT, purpose="具体情境")], []),
        _cand("A2", "BP_D1", ["simple", "full"], "运动用品区标志",
              "为学校的运动用品区设计一个标志，让同学看到它就知道这里放的是运动用的东西。图形和颜色由你决定。",
              "不一定要画球。", dict(NONE), d1_dims,
              [dict(requirement="场所：运动用品区", relation=PROJECT, purpose="同操作、换情境的对照候选")], ["题材 / 叙事"]),
        _cand("A1", "BP_D2", ["simple", "full"], "一片叶子",
              "照着图，把这片叶子画下来：它的形状、颜色，还有叶脉的纹路。",
              "先画轮廓，再画叶脉，最后上色。", dict(kind="reference", id="d2_nature_a", mode="always", spec=DRAFT_MATERIALS["d2_nature_a"]), d2_dims,
              [dict(requirement="对象：叶子", relation=PROJECT, purpose="具体对象")], []),
        _cand("A2", "BP_D2", ["simple", "full"], "一只贝壳",
              "照着图，把这只贝壳画下来：它的形状、颜色，还有表面的纹路。",
              "纹路是一圈一圈的，还是一条一条的？", dict(kind="reference", id="d2_nature_b", mode="always", spec=DRAFT_MATERIALS["d2_nature_b"]), d2_dims,
              [dict(requirement="对象：贝壳", relation=PROJECT, purpose="同操作、换对象的对照候选")], ["材料", "题材 / 叙事"]),
    ]
