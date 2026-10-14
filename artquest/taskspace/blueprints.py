# -*- coding: utf-8 -*-
"""蓝图：一类任务的规格（ECD 的 task model），不是主题列表，也不是单道题的标题。

每条蓝图回答六个问题：适用什么学段？主要学习目标？学生进行什么操作？必须提供什么输入？
必须保留什么产出？什么条件不能随意改变？——固定的是**活动结构**，不是创作答案。

学段：先沿用来源里的学段（`band_source`）；本项目实际分的是两版（simple = 小学、full = 初中，见
missions_v2），没有直接学段依据的改编标「拟适用」并写明理由（`band_proposed`）。
任务负担记具体组成（比较几个方案 / 空间关系 / 阅读文字 / 修改已有内容），不填难度数字。
"""
from typing import Any, Dict, List

from .sources import VERBATIM, ADAPTED, PROJECT

# 五种操作：工作索引，不是把所有资料硬塞进去的格子；色彩 / 线条 / 构图是跨操作的内容属性
OPERATIONS: Dict[str, str] = {
    "observe_represent": "观察与表现：看着真实或给定的对象，按其结构 / 关系表现出来",
    "personal_expression": "个人表达：按自己的想法用造型元素表达所见所闻所感所想",
    "purposeful_design": "有目的的设计：为一个明确用途 / 功能设计一个方案",
    "diverse_ideation": "多样化构想：对同一问题产生多个不同的方案",
    "evaluate_improve": "评价与改进：在已有方案上发现不足并改进",
}
CONTENT_ATTRIBUTES = ("color", "line", "composition", "space_perspective", "deformation_methods", "fusion", "constraint_rules", "narrative")

# 现有产品能力：任务要求的操作必须由工具 + 实际材料共同支持（Step 4.2）。这是事实清单，不是愿望清单。
CAPABILITIES: Dict[str, bool] = {
    "single_canvas_drawing": True,     # 一块 1024×704 画布，一次创作一幅
    "reference_always_visible": True,  # 参考图常显（mode=always）
    "reference_on_demand": True,       # 参考图默认收起，点开看（mode=on_demand）
    "vector_stimulus_on_canvas": True, # M3 碎片：印在初始画布上，橡皮擦回初始画布而不是白
    "colour_palette_everywhere": True, # 调色板在每个任务里都在；allowed_tools 只禁四个笔刷按钮
    "two_phase_metadata": True,        # M7 的 phases 只是元数据：客户端不按秒切换、不计时
    "multi_sketch_output": False,      # 不能在一局里保存多个方案 / 多张草图
    "movable_objects": False,          # 起始画面上的元素不能被拖动 / 重排，只能覆盖着画
    "editable_starting_artwork": False,# 没有「起始作品」类材料（画布要么空、要么印碎片）
    "text_input": False,               # 不收文字答案（彩点的窗也没有输入框）
    "timer": False,                    # 所有任务取消限时（2026-10-05）
}

SIMPLE, FULL = "simple", "full"


def _req(text: str, relation: str, source: str = "", purpose: str = "",
         support: str = "支持", span: str = "") -> Dict[str, str]:
    """一条设计要求 + 它的来源关系。项目新增条件必须说用途（purpose），否则检查会拦。

    `support` 是人判的（2026-10-12 来源核查后加的）：支持 = 片段明确说了这件事；部分 = 只说了一部分；
    间接 = 相关但不是对这项活动的规定。检查 S6 只对「支持」记「找到支持」，别的记成未决的提醒。
    `span`="大" 标「改编」离原文很远（课标说「改进生活用品」，题目是「茶壶变救援机」）。"""
    return {"requirement": text, "relation": relation, "excerpt": source, "purpose": purpose,
            "support": support, "span": span}


BLUEPRINTS: Dict[str, Dict[str, Any]] = {
    "BP_M1": dict(
        family="M1", title="照着参考图把整幅场景重现出来",
        band_source=["二(3–5)", "三(6–7)"], band_proposed={SIMPLE: "小学（课标第二学段：近大远小、写实手法）", FULL: "初中（第三学段：写实手法、透视；第四学段写实仍在手法清单里）"},
        goal="观察一个给定场景，按原有位置与大小把整体结构重现出来（整幅、每样东西都在原位）",
        operation="observe_represent", content=["composition", "space_perspective"],
        inputs=dict(reference="scene（6–8 个可辨识物体、前中后三层）, mode=always", canvas="空白"),
        outputs=dict(count=1, form="单幅完整场景"),
        invariants=["参考图常显", "要求整幅重现、物体在原位", "单幅产出"],
        free=["线条粗细与风格", "是否上色", "细节取舍"],
        load=dict(compare_schemes=0, spatial_relations=True, read_text=False, modify_existing=False),
        source_relations=[
            _req("观察物体在空间中近大远小、了解透视", VERBATIM, "kb:p55:t2-perspective"),
            _req("采用写实手法表现", VERBATIM, "kb:p55:t2-methods"),
            _req("课标承认「临摹」是模仿与改变原作的手法之一（教学提示谈的是与抄袭的区别，不是对这项活动的规定）", ADAPTED, "kb:p58:copy-vs-change", support="间接"),
            _req("观察对象从真实空间改成一张给定的场景图（数字画布 + 参考图常显）", ADAPTED, "kb:p55:t2-perspective"),
            _req("「博物馆要重画这幅画」的叙事框架", PROJECT, purpose="给整幅复原一个理由；不改变观察与表现这个操作"),
            _req("每张场景图 6–8 个物体、三层纵深、无文字无商标", PROJECT, purpose="五张平行卷负荷对齐；合规（无商标）"),
        ]),
    "BP_M2": dict(
        family="M2", title="看准几样东西的大小、前后与遮挡，画下来",
        band_source=["二(3–5)", "三(6–7)"], band_proposed={SIMPLE: "小学（近大远小）", FULL: "初中（观察立体物品、透视区别）"},
        goal="观察少量物体之间的大小差、前后与遮挡关系并准确表现",
        operation="observe_represent", content=["space_perspective"],
        inputs=dict(reference="桌面静物：正好 4 个物体、正好 2 处遮挡、有大小差、有纵深, mode=always", canvas="空白"),
        outputs=dict(count=1, form="单幅观察记录"),
        invariants=["参考图常显", "保留四对象、两处遮挡、大小差与纵深的项目材料规格", "单幅产出。"],
        free=["是否上色", "背景是否画", "线条风格"],
        load=dict(compare_schemes=0, spatial_relations=True, read_text=False, modify_existing=False),
        source_relations=[
            _req("观察物体在空间中近大远小", VERBATIM, "kb:p55:t2-perspective"),
            _req("从不同角度观察立体物品，了解透视区别", VERBATIM, "kb:p60:t2-perspective"),
            _req("观察对象改为桌面静物照片 / 插画", ADAPTED, "kb:p55:t2-perspective"),
            _req("4 物体 · 2 遮挡 · 大小差 · 纵深", PROJECT, purpose="控制空间关系的数量，让五张平行卷可比"),
            _req("侦探 / 寻宝 / 机器人等叙事", PROJECT, purpose="给记录一个理由；不改变操作"),
        ]),
    "BP_M3": dict(
        family="M3", title="把画布上的碎片接着画成一幅完整的画",
        band_source=["一(1–2)", "二(3–5)", "三(6–7)"], band_proposed={SIMPLE: "小学（想象力、添加手法）", FULL: "初中（提出构想并灵活变通）"},
        goal="以不完整图形为起点进行想象与转化，把碎片整合进一幅完整画面",
        operation="personal_expression", content=["deformation_methods", "composition"],
        inputs=dict(reference="无参考图（明确配置）", canvas="初始画布印有 7 块矢量碎片（弧、点、线、角、曲线、缺口矩形）"),
        outputs=dict(count=1, form="单幅完整画面，碎片保留在画布上"),
        invariants=["碎片位于初始画布且不能擦除", "七类元件按A–E布局变化", "单幅产出。属于结构变式，未验证为心理测量平行卷。"],
        free=["用几块碎片", "碎片变成什么", "主题、颜色"],
        load=dict(compare_schemes=0, spatial_relations=False, read_text=False, modify_existing=True),
        source_relations=[
            _req("参考 Urban（2005）第 273 页的图形片段续画范式；本项目自行设计刺激材料和任务实例", ADAPTED, "urban2005:paradigm"),
            _req("美术学习始终要保持好奇心和想象力", VERBATIM, "kb:p53:t2-teach"),
            _req("课标承认「添加」是改变原作的手法之一（教学提示谈的是与抄袭的区别）", ADAPTED, "kb:p58:copy-vs-change", support="间接"),
            _req("碎片改为画布空间的矢量图元（客户端与回放同一实现）", PROJECT, purpose="replay = 初始画布 + 笔画；两端逐像素一致"),
            _req("梦 / 符号 / 壁画等叙事", PROJECT, purpose="给碎片一个来历；不规定碎片要变成什么"),
        ]),
    "BP_M4": dict(
        family="M4", title="把一件普通物品改造成另一种用途的东西",
        band_source=["一(1–2)", "三(6–7)"], band_proposed={SIMPLE: "小学（改进生活用品 → 改造，用途由题给）", FULL: "初中（夸张、变形手法；改造要满足功能条件）"},
        goal="从一件物品的特征发展新形象或用途，关注原物、形态变化与用途之间的联系；不预设部件对应。",
        operation="purposeful_design", content=["deformation_methods"],
        inputs=dict(reference="单件物品图，纯白底, mode=on_demand（默认收起）", canvas="空白"),
        outputs=dict(count=1, form="单幅改造后的物品"),
        invariants=["基础物品、目标功能（有时还有环境）由题给定", "单幅产出"],
        free=["保留哪些部分", "改造后的外形", "是否画环境", "颜色"],
        load=dict(compare_schemes=0, spatial_relations=False, read_text=False, modify_existing=False),
        source_relations=[
            _req("从外观和功能了解物品，提出改进", VERBATIM, "kb:p51:t3-intro"),
            _req("夸张、变形手法", VERBATIM, "kb:p60:t2-methods"),
            _req("「改进」扩展为「改造成另一种功能物」，用途由题指定", ADAPTED, "kb:p51:t3-req", support="部分", span="大",
                 purpose="课标原文是「提出改进意见，进行装饰和美化」；把雨伞改成潜水艇离它很远，这里只是借了「从功能了解物品并改动它」这个入口"),
            _req("基础物 × 环境 × 功能 三张卡组合", PROJECT, purpose="平行卷：改变题材、保持操作"),
            _req("「还要看得出原物」（base_form_preservation）", PROJECT, purpose="区分转化与另起炉灶；**只有 M4_J3 的文案写明了它**，其余题只在提示里暗示——见检查结果"),
        ]),
    "BP_M5": dict(
        family="M5", title="把两个不相干的概念合成一个新东西",
        band_source=["三(6–7)", "四(8–9)"], band_proposed={SIMPLE: "拟适用小学：题面只要求「合在一起、都能看出来」，不要求归类重组的术语", FULL: "初中（想象、联想、归类、重组）"},
        goal="概念整合：两个概念的特征都保留并连成一体，而不是并置",
        operation="personal_expression", content=["fusion", "deformation_methods"],
        inputs=dict(reference="无参考图（明确配置）", canvas="空白"),
        outputs=dict(count=1, form="单幅融合物"),
        invariants=["两个概念由题给定（ASCII 记进 condition）", "要求两者特征都能看出、合为一体", "单幅产出"],
        free=["哪个概念为主", "变成生物 / 建筑 / 交通工具", "颜色、场景"],
        load=dict(compare_schemes=0, spatial_relations=False, read_text=False, modify_existing=False),
        source_relations=[
            _req("通过想象、联想、归类、重组进行构思", VERBATIM, "kb:p68:t2-req"),
            _req("提出各种构想并灵活变通", VERBATIM, "kb:p61:t2-req"),
            _req("概念对由项目挑选、要求「合为一体不是并置」", PROJECT, purpose="把 conceptual integration 和 M4 的单物改造区分开"),
        ]),
    "BP_M6": dict(
        family="M6", title="保留场景，只改颜色和明暗，让它有另一种感觉",
        band_source=["二(3–5)", "三(6–7)", "四(8–9)"], band_proposed={SIMPLE: "小学（对比色 / 邻近色；冷暖感受）", FULL: "初中（冷暖、互补、对比；色彩情感特征）"},
        goal="用颜色与明暗（而不是新增内容）传达指定的气氛 / 温度 / 时间",
        operation="personal_expression", content=["color"],
        inputs=dict(reference="情绪中性、低饱和的场景图, mode=always", canvas="空白（孩子在参考图旁重画并改色）"),
        outputs=dict(count=1, form="单幅改色后的场景"),
        invariants=["参考图常显", "目标气氛写入condition", "用颜色与明暗表达。新增对象限制以各题“不加／尽量不加”的实际措辞为准", "单幅产出。"],
        free=["具体用哪些颜色", "明暗怎么分布", "画得多细"],
        load=dict(compare_schemes=0, spatial_relations=False, read_text=False, modify_existing=False),
        source_relations=[
            _req("体验不同色彩带来的不同感受；冷暖、互补、对比", VERBATIM, "kb:p60:t2-color"),
            _req("色彩情感特征", VERBATIM, "kb:p68:t2-color"),
            _req("对比色、邻近色", VERBATIM, "kb:p54:t2-color"),
            _req("「只改颜色和明暗、不加新东西」", PROJECT, purpose="把颜色变量从内容变量里隔离出来，让 color richness / contrast 真正可观察"),
            _req("参考图要情绪中性、低饱和", PROJECT, purpose="原图越平，改动越看得出"),
        ]),
    "BP_M7": dict(
        family="M7", title="先只用线条画一个抽象概念，再把这些线发展成一幅画",
        band_source=["一(1–2)", "四(8–9)"], band_proposed={SIMPLE: "小学（线条造型元素；概念是具体可感的：雨、弹跳、生长）", FULL: "初中（抽象手法；概念更内在：小声说话、沉重、紧张）"},
        goal="第一步用线条的疏密、方向、力度表达概念；第二步不擦掉这些线，把它们转化成有内容的画",
        operation="personal_expression", content=["line", "deformation_methods"],
        inputs=dict(reference="无参考图（明确配置）", canvas="空白"),
        outputs=dict(count=1, form="单幅最终画；第一步的线应保留在画中（由文案要求，不由工具保证）"),
        invariants=["概念由题给定", "第一步只用线条、不画具体物", "第二步不擦掉第一步的线", "单幅产出"],
        free=["线的样子", "第二步变成什么", "颜色"],
        load=dict(compare_schemes=0, spatial_relations=False, read_text=False, modify_existing=True),
        source_relations=[
            _req("线条等造型元素按自己的想法表达", VERBATIM, "kb:p50:t2-intro"),
            _req("抽象手法", VERBATIM, "kb:p68:t2-methods"),
            _req("两步结构（先抽象线条，再发展成作品）", PROJECT, purpose="把 line combination / texture 和后面的转化分开观察"),
            _req("「第一步（60 秒）」", PROJECT, purpose="只是引导语：程序不计时、不切换工具（2026-10-05 取消所有限时）"),
        ]),
    "BP_M8": dict(
        family="M8", title="按给定的两三条世界规则，画出这个世界里的生活",
        band_source=["三(6–7)", "四(8–9)"], band_proposed={SIMPLE: "拟适用小学：规则两条、用词具体（人比虫子小）", FULL: "初中：固定开头 + 两条 + 一条可选挑战"},
        goal="在给定世界规则下进行想象和场景组织；按题面区分必须规则与可选规则。",
        operation="personal_expression", content=["constraint_rules", "composition"],
        inputs=dict(reference="无参考图（明确配置）", canvas="空白"),
        outputs=dict(count=1, form="单幅世界场景"),
        invariants=["规则由题给定并记进 condition", "规则要在画里成立", "单幅产出"],
        free=["画哪一刻、哪个地方", "谁在里面", "颜色、风格"],
        load=dict(compare_schemes=0, spatial_relations=False, read_text=True, modify_existing=False),
        source_relations=[
            _req("想象、联想、重组", VERBATIM, "kb:p68:t2-req"),
            _req("「科学幻想」是课标列出的情境素材举例（教学提示里的举例，不是内容要求）", VERBATIM, "kb:p66:contexts", support="间接"),
            _req("世界规则生成器（两三条规则）", PROJECT, purpose="用可记录的约束替代自由命题，让 rule_coverage 可比"),
            _req("初中版可选第三条", PROJECT, purpose="给负担留一个可选台阶；可选项不进必要产出"),
        ]),
    "BP_M9": dict(
        family="M9", title="给一个故事开头，画出接下来发生的事",
        band_source=["一(1–2)", "二(3–5)", "三(6–7)"], band_proposed={SIMPLE: "小学", FULL: "初中"},
        goal="以开放故事起点观察叙事与场景组织；用于探索其他任务中的表现是否在不同情境出现。",
        operation="personal_expression", content=["narrative", "composition"],
        inputs=dict(reference="无参考图（明确配置）", canvas="空白"),
        outputs=dict(count=1, form="单幅叙事画面"),
        invariants=["故事开头由题给定", "单幅产出"],
        free=["画哪一刻", "有谁、在哪", "颜色、风格"],
        load=dict(compare_schemes=0, spatial_relations=False, read_text=False, modify_existing=False),
        source_relations=[
            _req("表达所见所闻、所感所想", VERBATIM, "kb:p54:t2-intro"),
            _req("「校园中的故事」是课标列出的情境素材举例（教学提示里的举例，不是内容要求）", VERBATIM, "kb:p66:contexts", support="间接"),
            _req("故事开头由项目给定", PROJECT, purpose="让不同孩子的画可比，同时保持开放"),
        ]),
    "BP_M0": dict(
        family="M0", title="自由创作（v1 基线，legacy）",
        band_source=[], band_proposed={SIMPLE: "—", FULL: "—"},
        goal="较开放的命题创作参照：保留主题起点，观察学生如何自主组织内容与表达。", operation="personal_expression", content=[],
        inputs=dict(reference="无", canvas="空白"), outputs=dict(count=1, form="单幅"),
        invariants=["旧 id 不改"], free=["一切"],
        load=dict(compare_schemes=0, spatial_relations=False, read_text=False, modify_existing=False),
        source_relations=[_req("表达所见所闻、所感所想", VERBATIM, "kb:p50:t2-intro")]),
}

# ---- 首访任务库（2026-10-12，docs/Task_Library_zh_CN.md v1.0.0）的五个家族 ----
# 这些蓝图的学段来自文档的年龄段表；每道题自己的「必要条件 / 自由空间 / 九维关联 / 明确的改编内容」在 bank JSON 里，
# 候选直接读那里（candidates._bank_candidate），这里只定家族层面的操作、输入、产出和共用的来源关系。
_BANK_COMMON = [
    _req("全部任务从空白画布开始，提交一幅作品；参考图在参考区常显、不粘贴进作品", PROJECT, purpose="first_visit_common_v1：首稿一幅、材料不混入作品"),
    _req("参考 PNG 1600×1200、contain 完整显示，不裁掉叶柄 / 车轮 / 笔筒底", PROJECT, purpose="材料条件：孩子看到的就是检查过的那张"),
    _req("没有 60 秒阶段、不限时；提示固定、按需显示、记显示事件", PROJECT, purpose="提示是过程支持，不产生新的必须条件"),
    _req("允许单色、不要求写字；修改轮和 M 族一样都有（2026-10-12 用户定：refine 不能有时有有时没有）", PROJECT, purpose="颜色丰富度和文字长度不是通用完成门槛"),
]
BLUEPRINTS.update({
    "BP_OB": dict(family="OB", title="首访 · 观察与表现：看着参考图画出对象及其关系", bank=True,
                  band_source=["一(1–2)", "二(3–5)", "三(6–7)", "四(8–9)", "高中起始", "17+（无学段，取自 M 族题库）"], band_proposed={"B1": "6–7 两片叶子", "B2": "8–10 三件物品 + 一处遮挡", "B3": "11–12 四件物品 + 两处前后", "B4": "13–14 窗边静物", "B5": "15–16 街角两个面", "B6": "17+ 整个客厅（M1_J5）"},
                  goal="用共同参考比较外形与关系；复杂度按对象数和关系数描述，不是实测难度",
                  operation="observe_represent", content=["space_perspective", "line"],
                  inputs=dict(reference="单张参考 PNG（1600×1200），always，contain", canvas="空白"),
                  outputs=dict(count=1, form="单幅观察画"),
                  invariants=["参考图常显且完整显示", "题面点名的对象和关系要出现", "单幅产出", "允许单色"],
                  free=["线稿或上色", "整体大小", "省略细节"],
                  load=dict(compare_schemes=0, spatial_relations=True, read_text=False, modify_existing=False),
                  source_relations=[_req("观赏自然对象，感知其形状美、色彩美和肌理美", VERBATIM, "kb:p49:t1-nature"),
                                    _req("观察空间中的近大远小", VERBATIM, "kb:p55:t2-perspective"),
                                    _req("观察对象改为参考图而非实物", ADAPTED, "kb:p55:t2-perspective")] + _BANK_COMMON),
    "BP_ST": dict(family="ST", title="首访 · 个人表达与叙事：一幅画表现一件事或一种理解", bank=True,
                  band_source=["一(1–2)", "二(3–5)", "三(6–7)", "四(8–9)", "高中起始", "17+（无学段，取自 M 族题库）"], band_proposed={"B1": "一起玩", "B2": "放学以后", "B3": "一件意外的事", "B4": "同一个地方的两种感觉", "B5": "距离", "B6": "地图上的地方（M9_J5）"},
                  goal="用形象、动作、布局表达一个生活 / 想象情境或一个概念；单幅、不写故事",
                  operation="personal_expression", content=["narrative", "composition"],
                  inputs=dict(reference="无参考图（明确配置）", canvas="空白"),
                  outputs=dict(count=1, form="单幅叙事 / 表达画"),
                  invariants=["单幅", "题面要求的人物 / 动作 / 对比要出现", "不要求写字"],
                  free=["真实或想象", "颜色、背景", "人物画法"],
                  load=dict(compare_schemes=0, spatial_relations=False, read_text=False, modify_existing=False),
                  source_relations=[_req("按自己的想法表达所见所闻所感所想", VERBATIM, "kb:p50:t2-intro"),
                                    _req("表现自己的所见所闻、所感所想，以视觉形象与人交流", VERBATIM, "kb:p54:t2-intro"),
                                    _req("创造性地表达对自然与社会的感受、思考和认识", VERBATIM, "kb:p68:t2-intro")] + _BANK_COMMON),
    "BP_FG": dict(family="FG", title="首访 · 图形片段创作：把参考区的原创片段画进一幅画并发展它", bank=True,
                  band_source=["一(1–2)", "二(3–5)", "三(6–7)", "四(8–9)", "高中起始", "17+（无学段，取自 M 族题库）"], band_proposed={"B1": "一段弯线", "B2": "两段线条同一场景", "B3": "三段线条一个地方", "B4": "四段线条一个角色", "B5": "四段线条「连接」主题", "B6": "七块碎片的壁画（M3 组 E）"},
                  goal="从模糊图形刺激发展个人构想；片段在参考区，由孩子转抄到空白画布（不印在画布上，不是 TCT-DP 原题）",
                  operation="personal_expression", content=["deformation_methods", "composition"],
                  inputs=dict(reference="片段参考 PNG（+ 可编辑 SVG），always，contain", canvas="空白"),
                  outputs=dict(count=1, form="单幅画，原片段仍能被找到"),
                  invariants=["所有片段须可辨认", "转抄时可调整位置、方向和大小", "单幅产出。不表示需要可移动对象工具。"],
                  free=["片段变成什么", "主题", "颜色"],
                  load=dict(compare_schemes=0, spatial_relations=False, read_text=False, modify_existing=False),
                  source_relations=[_req("以给定的图形片段为基础完成一幅画", ADAPTED, "urban2005:paradigm"),
                                    _req("美术学习始终要保持好奇心和想象力", VERBATIM, "kb:p53:t2-teach"),
                                    _req("课标承认「添加」是改变原作的手法之一（教学提示谈的是与抄袭的区别）", ADAPTED, "kb:p58:copy-vs-change", support="间接"),
                                    _req("片段原创、参考区呈现、自由手绘转抄（和 M3 印在画布上不同）", PROJECT, purpose="不复制原测验题纸、边框、计时或评分；转抄是额外的操作负担，分析时记着")] + _BANK_COMMON),
    "BP_TR": dict(family="TR", title="首访 · 物品创意改造：把参考物品变成有新用途的东西并保留可辨认特征", bank=True,
                  band_source=["一(1–2)", "二(3–5)", "三(6–7)", "四(8–9)", "高中起始", "17+（无学段，取自 M 族题库）"], band_proposed={"B1": "会帮忙的杯子", "B2": "雨伞的新本领", "B3": "茶壶救援机", "B4": "自行车的新用途", "B5": "小空间台灯", "B6": "鞋子变生物（M4_J3）"},
                  goal="把熟悉物品的特征和一个新用途联系起来；「保留可辨认特征」写在题面里，不是隐藏要求",
                  operation="purposeful_design", content=["deformation_methods"],
                  inputs=dict(reference="单件物品 PNG，always，contain（参考图不含改造答案）", canvas="空白"),
                  outputs=dict(count=1, form="单幅改造物 + 使用方式"),
                  invariants=["从参考物品出发", "画出怎样使用 / 帮忙", "保留可辨认特征（不指定部件）", "单幅"],
                  free=["用途现实或幻想", "保留哪些部分", "是否画场景"],
                  load=dict(compare_schemes=0, spatial_relations=False, read_text=False, modify_existing=False),
                  source_relations=[_req("从外观和功能了解物品，提出改进", VERBATIM, "kb:p51:t3-intro"),
                                    _req("夸张、变形手法", VERBATIM, "kb:p60:t2-methods"),
                                    _req("「改进」扩展为「改造成新用途」，用途由题给定或由孩子选", ADAPTED, "kb:p51:t3-req", support="部分", span="大",
                                         purpose="课标原文是「提出改进意见，进行装饰和美化」；B2 雨伞、B4 自行车、B5 台灯是真的改进，B1 杯子、B3 茶壶、B6 鞋子离原文远")] + _BANK_COMMON),
    "BP_DS": dict(family="DS", title="首访 · 视觉传达设计：为一个明确用途做标志 / 吉祥物 / 海报", bank=True,
                  band_source=["一(1–2)", "二(3–5)", "三(6–7)", "四(8–9)", "高中起始", "17+（无学段，取自 M 族题库）"], band_proposed={"B1": "玩具箱标志", "B2": "图书角标志", "B3": "运动会吉祥物", "B4": "校园活动海报", "B5": "校园少浪费海报", "B6": "我的画廊标志"},
                  goal="让图像为一个明确用途服务；不要求文字、不要求真实校名日期",
                  operation="purposeful_design", content=["composition"],
                  inputs=dict(reference="无参考图（明确配置）", canvas="空白"),
                  outputs=dict(count=1, form="单幅标志 / 吉祥物 / 海报"),
                  invariants=["回应题面给定的用途", "单幅", "不要求写字"],
                  free=["图形、颜色", "是否加标题", "角色类型"],
                  load=dict(compare_schemes=0, spatial_relations=False, read_text=False, modify_existing=False),
                  source_relations=[_req("为班级或学校的活动设计标识、请柬、贺卡、图表、海报", VERBATIM, "kb:p56:t3-visual-design"),
                                    _req("用画笔或计算机做有明确用途的小设计", VERBATIM, "kb:p52:t5-design"),
                                    _req("根据不同活动的需要设计海报、请柬", VERBATIM, "kb:p62:t3-improve")] + _BANK_COMMON),
})

# 课标里有、本库还没有蓝图的操作 / 情境——保留缺口比用相似题填满更有用（Step 1.5）
GAPS: List[Dict[str, Any]] = [
    dict(operation="diverse_ideation", excerpts=["kb:p55:t2-req", "kb:p61:t2-req", "pisa:processes"],
         why_missing="没有任何家族要求产出多个方案；产品也没有一局保存多张草图的能力（CAPABILITIES.multi_sketch_output=False）",
         needs=["multi_sketch_output"], note="PISA 的「产生多样构想」依据尚未录入原文"),
    dict(operation="evaluate_improve", excerpts=["kb:p55:t3-improve", "kb:p62:t3-improve", "pisa:dt200q02"],
         why_missing="没有「起始作品」类材料，也不能移动起始画面上的对象；M3 碎片是起点不是待改进的方案",
         needs=["editable_starting_artwork", "movable_objects"], note="DT200Q02 原文未录入"),
    dict(operation="purposeful_design", excerpts=["kb:p56:t3-visual-design", "kb:p52:t5-design"],
         why_missing="校园情境的视觉设计（标识 / 海报 / 请柬）没有蓝图；M4 的「有目的的设计」是物品改造，不是校园视觉设计",
         needs=[], note="可以直接起草：空白画布 + 单幅产出 + 无参考图，现有能力已够；示例规格见 docs/任务初始化.md"),
    dict(operation="observe_represent", excerpts=["kb:p49:t1-nature"],
         why_missing="观察自然对象的形状 / 色彩 / 肌理（第一学段）没有蓝图；M1/M2 的对象都是室内外人造场景或静物",
         needs=[], note="需要新的参考图材料规格"),
]


# 流程层的来源（2026-10-12）：这两份文献支撑的不是某道题，是流程和评分，所以不挂在任何题上。
#   PISA 的三个侧面里「评价与改进」对应画完一轮、看完反馈再改的进化关；「产生创意构想」对应一次只交一幅。
#   KidsArtBench 只支撑九维评分量表，不支撑题目。
FLOW_SOURCES: List[Dict[str, str]] = [
    dict(where="进化关（画完 → 反馈 → 修改）", excerpt="pisa:processes", note="evaluate and improve ideas"),
    dict(where="一次只交一幅", excerpt="pisa:processes", note="generate creative ideas（不要求多方案）"),
    dict(where="九维评分", excerpt="kab:table1", note="量表来源；评作品，不评任务"),
]
