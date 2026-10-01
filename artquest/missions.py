# -*- coding: utf-8 -*-
"""Creative Mission library — the task as a *measurement object*.

Backstage a task is an experimental condition; to the child it is a mission.
The child should never think "now they are measuring my imagination", only
"I have an interesting problem to solve" — so every family carries a narrative
prompt bank, and the research metadata rides underneath the same row.

A task here knows all six things at once:

    what behaviour it is built to elicit   (`research_goal`, `process_targets`)
    which 9D attributes it speaks to       (`rubric`, see `rubric.py`)
    which it cannot speak to               (`not_applicable_dimensions` + reason)
    which parallel form it is              (`family` + `form_id`)
    under what condition it runs           (`time_limit_sec`, `allowed_tools`, stimulus)
    what the child is shown                (`instruction`, `prompt_style`)

Form ids are stable and meaningful (`M4_UMB_UW_TRA_story`), because a task id is
a foreign key in every table that follows and must keep meaning the same thing
after the library grows. Generated families enumerate a curated cross-product;
researchers add more combinations through `tasks.json` using the same id scheme.
"""
from typing import Any, Dict, List, Optional

# -- narrative cards shared by the generated families ------------------------
M4_BASE = [("umbrella", "UMB", "雨伞"), ("shoe", "SHO", "鞋子"), ("backpack", "BAG", "背包"),
           ("chair", "CHA", "椅子"), ("teapot", "TEA", "茶壶"), ("clock", "CLO", "时钟"),
           ("lamp", "LAM", "台灯"), ("bicycle", "BIC", "自行车")]
M4_ENV = [("underwater", "UW", "海底"), ("outer space", "OS", "太空"), ("desert", "DS", "沙漠"),
          ("frozen world", "FZ", "冰封世界"), ("giant forest", "GF", "巨大的森林"),
          ("floating city", "FC", "漂浮的城市")]
M4_GOAL = [("transportation", "TRA", "交通工具"), ("shelter", "SHE", "庇护所"),
           ("creature", "CRE", "生物"), ("rescue machine", "RES", "救援机器"),
           ("home", "HOM", "家"), ("exploration tool", "EXP", "探索工具")]

# curated combinations: parallel forms that stay comparable to each other
M4_COMBOS = [("umbrella", "underwater", "transportation"), ("teapot", "outer space", "rescue machine"),
             ("shoe", "giant forest", "creature"), ("backpack", "frozen world", "shelter"),
             ("chair", "floating city", "home"), ("clock", "desert", "exploration tool")]

M5_PAIRS = [("castle", "jellyfish", "城堡", "水母"), ("cat", "airplane", "猫", "飞机"),
            ("train", "tree", "火车", "树"), ("robot", "flower", "机器人", "花"),
            ("shoe", "house", "鞋子", "房子"), ("whale", "school", "鲸鱼", "学校"),
            ("backpack", "bird", "背包", "鸟"), ("clock", "octopus", "时钟", "章鱼")]

M7_CONCEPTS = [("wind", "风"), ("whisper", "耳语"), ("explosion", "爆炸"), ("rain", "雨"),
               ("speed", "速度"), ("heavy", "沉重"), ("nervous", "紧张"), ("calm", "平静"),
               ("bouncing", "弹跳"), ("growing", "生长")]

M8_RULES = {
    "physics": ["重力是横着的。", "水漂浮在天上。", "影子会自己走动。", "夜里所有东西都会变轻。"],
    "scale": ["植物比建筑还大。", "人比昆虫还小。", "一座山能装进一间屋子里。"],
    "life": ["房子是活的。", "动物建造城市。", "人需要的时候会长出翅膀。", "机器和植物住在一起。"],
    "environment": ["整座城市在水下。", "所有人住在云层之上。", "世界在一棵巨树里面。", "地面是会移动的岛。"],
}
M8_SETS = [("R01", ["physics:0", "scale:1"]), ("R02", ["life:0", "environment:2"]),
           ("R03", ["physics:1", "life:3", "scale:0"]), ("R04", ["environment:0", "physics:2"]),
           ("R05", ["scale:2", "life:1", "environment:3"]), ("R06", ["physics:3", "environment:1"])]

M3_NARRATIVE = ["有什么刚刚抵达。", "有什么正躲着。", "这里正在庆祝。",
                "有什么就要改变了。", "这里有个东西不属于这儿。"]

DRAW_TOOLS = ["pencil", "eraser", "undo", "redo", "zoom"]
COLOR_TOOLS = ["pencil", "brush", "marker", "eraser", "undo", "redo", "zoom"]


def _fragments(seed: str) -> Dict[str, Any]:
    """M3's incomplete figures, as canvas-space primitives.

    Vector, not a bitmap, so the client and the replayer draw the identical
    starting canvas — replay is `initial canvas + strokes + events`, and the
    initial canvas is not blank for this family.
    """
    banks = {
        "A": [{"type": "arc", "cx": 260, "cy": 210, "r": 90, "a0": 200, "a1": 20},
              {"type": "dot", "x": 620, "y": 160, "r": 7}, {"type": "dot", "x": 680, "y": 205, "r": 7},
              {"type": "line", "x1": 780, "y1": 120, "x2": 880, "y2": 260},
              {"type": "corner", "x": 200, "y": 470, "w": 150, "h": 120},
              {"type": "curve", "x1": 460, "y1": 520, "cx": 590, "cy": 420, "x2": 720, "y2": 540},
              {"type": "rect_open", "x": 800, "y": 430, "w": 160, "h": 130, "gap": "top"}],
        "B": [{"type": "arc", "cx": 760, "cy": 240, "r": 100, "a0": 40, "a1": 250},
              {"type": "dot", "x": 300, "y": 180, "r": 7}, {"type": "dot", "x": 360, "y": 250, "r": 7},
              {"type": "line", "x1": 150, "y1": 300, "x2": 300, "y2": 180},
              {"type": "corner", "x": 620, "y": 470, "w": 170, "h": 110},
              {"type": "curve", "x1": 180, "y1": 540, "cx": 330, "cy": 440, "x2": 470, "y2": 560},
              {"type": "rect_open", "x": 120, "y": 60, "w": 150, "h": 120, "gap": "right"}],
        # v2.2（2026-10-01）再加三组，和 A/B 一样七块、一样的元件种类，只是摆法不同
        "C": [{"type": "arc", "cx": 520, "cy": 180, "r": 110, "a0": 160, "a1": 380},
              {"type": "dot", "x": 160, "y": 420, "r": 7}, {"type": "dot", "x": 230, "y": 390, "r": 7},
              {"type": "line", "x1": 700, "y1": 520, "x2": 900, "y2": 400},
              {"type": "corner", "x": 100, "y": 120, "w": 140, "h": 130},
              {"type": "curve", "x1": 300, "y1": 600, "cx": 480, "cy": 480, "x2": 640, "y2": 620},
              {"type": "rect_open", "x": 760, "y": 90, "w": 170, "h": 120, "gap": "bottom"}],
        "D": [{"type": "arc", "cx": 300, "cy": 520, "r": 95, "a0": 300, "a1": 120},
              {"type": "dot", "x": 560, "y": 110, "r": 7}, {"type": "dot", "x": 610, "y": 160, "r": 7},
              {"type": "line", "x1": 120, "y1": 200, "x2": 330, "y2": 260},
              {"type": "corner", "x": 700, "y": 300, "w": 160, "h": 120},
              {"type": "curve", "x1": 520, "y1": 560, "cx": 700, "cy": 640, "x2": 880, "y2": 540},
              {"type": "rect_open", "x": 400, "y": 60, "w": 130, "h": 110, "gap": "left"}],
        "E": [{"type": "arc", "cx": 820, "cy": 480, "r": 105, "a0": 120, "a1": 330},
              {"type": "dot", "x": 420, "y": 300, "r": 7}, {"type": "dot", "x": 470, "y": 360, "r": 7},
              {"type": "line", "x1": 160, "y1": 560, "x2": 360, "y2": 460},
              {"type": "corner", "x": 560, "y": 120, "w": 150, "h": 120},
              {"type": "curve", "x1": 120, "y1": 160, "cx": 300, "cy": 60, "x2": 440, "y2": 190},
              {"type": "rect_open", "x": 760, "y": 160, "w": 160, "h": 130, "gap": "top"}],
    }
    return {"kind": "fragments", "seed": seed, "stimulus_id": f"m3_fragments_{seed.lower()}",
            "items": banks[seed], "stroke": "#3a3a3a", "width": 3}


def _reference(path: str, sid: str, mode: str = "always") -> Dict[str, Any]:
    return {"kind": "reference", "stimulus_id": sid, "id": sid, "file": path, "mode": mode}


def _t(**kw: Any) -> Dict[str, Any]:
    return kw


# ---------------------------------------------------------------------------
# M1 — Museum Restorer
# ---------------------------------------------------------------------------
M1_PROMPTS = [
    ("A", "博物馆抢修", "博物馆的一幅画损坏了。请根据参考图把重要的物体、位置和结构重新画出来，让别人还能认出原来的场景。"),
    ("B", "探险家丢失的照片", "探险队的一张照片坏掉了。请重新画出这个地方，让下一位探险家知道这里有什么，以及它们分别在哪里。"),
    ("C", "侦探的现场重建", "侦探只找到了一张损坏的现场图片。请把重要结构重新画出来，让其他侦探能够理解这个场景。"),
    ("D", "机器人的记忆修复", "一个机器人只剩下这个地方的视觉记录。请帮助它重新建立这个场景。"),
]

M2_PROMPTS = [
    ("A", "外星观察日志", "你第一次来到一个陌生星球。画一张观察记录，让下一位探险家知道这些东西长什么样、谁在前面、谁在后面。"),
    ("B", "科学家的速写本", "你是一名科学家。请准确记录这些物体的大小、形状和相互位置。"),
    ("C", "寻宝现场", "这是寻宝地图中的重要现场。请记录物体的位置和遮挡关系，让另一个人能够重新摆出这个场景。"),
    ("D", "教机器人看东西", "一个机器人不会理解空间。请画出这个场景，让它知道哪个物体更大、哪个更近、哪个被挡住。"),
]

M3_PROMPTS = [
    ("A", "丢失的画", "我们只找到了原画留下来的几个碎片。把它们变成一幅完整的画，并告诉我们这里发生了什么。"),
    ("B", "神秘讯息", "有人留下了一些奇怪符号。也许它们其实属于一个更大的世界。把它们发展成一幅完整作品。"),
    ("C", "梦的碎片", "这些图形是一个梦留下来的碎片。请把它们变成完整的梦境。"),
    ("D", "故障的传送门", "一个传送门发生故障，只留下这些视觉碎片。画出另一边原来是什么地方。"),
]

M5_PROMPTS = [
    ("A", "混种生物", "把两种完全不同的东西融合成一种新的生物。不要只是放在一起，要让它们真的成为一个整体。"),
    ("B", "未来发明", "把这两个东西融合成一种未来的发明。"),
    ("C", "不可能的建筑", "如果这两个东西一起变成一栋建筑，它会是什么样？"),
    ("D", "双重身份", "设计一个新东西，让人第一眼看到 A，仔细看又发现它同时也是 B。"),
]

# variants carry an ASCII key: a task_id is a foreign key in every later table
# and ends up in filenames and CSV headers
M6_PROMPTS = [
    ("A", "情绪开关", "把这个普通场景变得{mood}。",
     [("calm", "平静"), ("mysterious", "神秘"), ("exciting", "兴奋"), ("dangerous", "危险")]),
    ("B", "天气魔法师", "让这个地方看起来像一场暴风雨即将来临。", None),
    ("C", "两个世界", "同一画面里，一边安全、一边危险。用颜色和视觉变化让人一眼看出区别。", None),
    ("D", "藏起来的主角", "用颜色让观众第一眼注意到最重要的对象，但不要把其他部分全部变暗。", None),
    ("E", "时光机", "把这个地方变成{when}。",
     [("midnight", "午夜"), ("sunrise", "日出"), ("other_planet", "另一个星球"),
      ("after_100_years", "一百年后")]),
]

M7_PROMPTS = [
    ("A", "有魔法的线", "这些线条突然有了魔法。它们变成了什么？"),
    ("B", "画声音的人", "如果一个声音能被看见，它会是什么样？再把它发展成完整画面。"),
    ("C", "线条怪物", "你刚才画的线突然活了。它们变成了一个怎样的世界？"),
]

M9_PROMPTS = [
    ("A", "没见过的门", "你打开一扇从未见过的门。门后面有什么？"),
    ("B", "全都变小了", "某天城市里的所有东西突然变小了，只有一样东西保持原来大小。"),
    ("C", "会说话的东西", "一个普通物品突然学会说话。它最想做什么？"),
    ("D", "天空里的东西", "天空突然出现了一个没有人见过的东西。发生了什么？"),
    ("E", "不存在的地方", "你发现了一张地图，上面标着一个不存在的地方。画出你最终找到的地方。"),
]


# ---------------------------------------------------------------------------
# Family definitions: what each mission measures, and under what condition
# ---------------------------------------------------------------------------
# 每幅画的九个维度都会评分。`primary` / `secondary` 说的是这个任务**额外**要
# 考察什么——它决定界面的高亮、「这一关练的是」和彩点哪几项属性会长，
# 不决定哪些维度会被打分。想「不评某个维度」是做不到的：`not_applicable` 只能
# 由任务自己的条件推出来（见 rubric.condition_na），而且现在没有任务够得着它——
# 调色板在每个任务里都在，`allowed_tools` 限制的是四个笔刷按钮，铅笔照样
# 用孩子选的颜色画。
FAMILIES: Dict[str, Dict[str, Any]] = {
    # M0 keeps the original open-creation quests alive. Sessions already
    # collected against these ids must stay interpretable — the library grew,
    # it did not replace what was measured before.
    "M0": _t(
        slug="open_creation", name="自由创作", icon="🎨", color="#f79433", difficulty=2,
        research_goal="开放创作：每个研究字段取宽松值，是合法条件取值而不是缺字段",
        time_limit_sec=None, allowed_tools=None, prompt_style="story", legacy=True,
        rubric=_t(),          # everything exploratory: the task claims nothing
        process_targets=["planning_latency", "new_element_count", "region_switching"]),
    "M1": _t(
        slug="museum_restorer", name="博物馆修复师", icon="🏛", color="#4db8ef", difficulty=2,
        research_goal="visual organization、global/local strategy、reference-based reconstruction",
        time_limit_sec=540, allowed_tools=DRAW_TOOLS, prompt_style="story",
        rubric=_t(primary_dimensions=["realism", "picture_organization", "line_combination"],
                  secondary_dimensions=["line_texture"]),
        process_targets=["first_stroke_region", "global_structure_time", "detail_entry_time",
                         "region_switching", "structural_revision", "erase_redraw_cycle",
                         "reference_switching"]),
    "M2": _t(
        slug="explorer_field_sketch", name="探险家速写", icon="🔭", color="#6cc24a", difficulty=2,
        research_goal="observation + spatial reasoning + reference strategy",
        time_limit_sec=540, allowed_tools=DRAW_TOOLS, prompt_style="story",
        rubric=_t(primary_dimensions=["realism", "picture_organization"],
                  secondary_dimensions=["line_combination", "line_texture"]),
        process_targets=["object_order", "layout_establishment_time", "proportion_revision",
                         "overlap_revision", "reference_viewing", "canvas_reference_switch",
                         "region_switching"]),
    "M3": _t(
        slug="lost_fragment_story", name="失落的碎片", icon="🧩", color="#b98cf0", difficulty=3,
        research_goal="incomplete-figure creativity（TCT-DP / TTCT 范式，刺激自制）",
        time_limit_sec=600, allowed_tools=COLOR_TOOLS, prompt_style="story",
        rubric=_t(primary_dimensions=["imagination", "transformation", "picture_organization"],
                  secondary_dimensions=["deformation", "line_combination"]),
        process_targets=["planning_latency", "first_fragment_used", "fragment_integration_order",
                         "new_element_count", "large_revision", "idea_shift",
                         "boundary_expansion", "premature_closure"]),
    "M4": _t(
        slug="mutant_object_lab", name="变异物体实验室", icon="🔧", color="#f2706e", difficulty=3,
        research_goal="deformation + transformation + imagination",
        time_limit_sec=720, allowed_tools=COLOR_TOOLS, prompt_style="story",
        rubric=_t(primary_dimensions=["deformation", "transformation", "imagination"],
                  secondary_dimensions=["picture_organization", "line_combination"]),
        process_targets=["first_transformation_time", "base_form_preservation", "semantic_shift",
                         "alternative_attempts", "structural_revision", "erase_rebuild"]),
    "M5": _t(
        slug="fusion_inventor", name="融合发明家", icon="🧬", color="#ef85b0", difficulty=3,
        research_goal="conceptual integration（与 M4 的「改造单一物体」是不同 construct）",
        time_limit_sec=720, allowed_tools=COLOR_TOOLS, prompt_style="story",
        rubric=_t(primary_dimensions=["transformation", "deformation", "imagination"],
                  secondary_dimensions=["picture_organization"]),
        process_targets=["dominant_base_choice", "second_concept_entry_time",
                         "juxtaposition_to_integration", "structural_reorganization",
                         "dominance_reversal"]),
    "M6": _t(
        slug="mood_world", name="情绪世界", icon="🎨", color="#45c4a8", difficulty=2,
        research_goal="让 color richness / contrast 真正 observable：不给「多用颜色」的指令，而给颜色一个表达任务",
        time_limit_sec=600, allowed_tools=COLOR_TOOLS, prompt_style="story",
        rubric=_t(primary_dimensions=["color_richness", "color_contrast"],
                  secondary_dimensions=["picture_organization", "line_texture"]),
        process_targets=["palette_breadth", "first_color", "color_introduction_order",
                         "recolor_frequency", "contrast_edit", "focal_recolor",
                         "local_global_color_order"]),
    "M7": _t(
        slug="line_adventure", name="线条冒险", icon="〰️", color="#5b8fd6", difficulty=2,
        research_goal="line combination / texture，两阶段：先抽象线条，再发展成完整作品",
        time_limit_sec=600, allowed_tools=COLOR_TOOLS, prompt_style="story",
        phases=[_t(id="lines", label="只用线条", seconds=60,
                   allowed_tools=["pencil", "undo", "redo"],
                   rubric_focus=["line_combination", "line_texture"]),
                _t(id="develop", label="发展成作品", seconds=540, allowed_tools=COLOR_TOOLS,
                   rubric_focus=["transformation", "imagination", "picture_organization"])],
        rubric=_t(primary_dimensions=["line_combination", "line_texture", "transformation",
                                      "imagination"],
                  secondary_dimensions=["picture_organization"]),
        process_targets=["stroke_length_distribution", "curvature", "direction_diversity",
                         "density", "repetition", "pressure", "layering", "rhythm",
                         "line_preservation", "line_reinterpretation", "semantic_conversion_time"]),
    "M8": _t(
        slug="impossible_world", name="不可能世界", icon="🌀", color="#9b86ee", difficulty=4,
        research_goal="最接近 authentic art creation，但由 world-rule generator 约束",
        time_limit_sec=1080, allowed_tools=COLOR_TOOLS, prompt_style="story",
        # the only family where every dimension can be elicited at once
        rubric=_t(primary_dimensions=["imagination", "transformation", "picture_organization"],
                  secondary_dimensions=["realism", "deformation", "color_richness",
                                        "color_contrast", "line_combination", "line_texture"]),
        process_targets=["planning_latency", "rule_coverage", "idea_shift", "large_revision",
                         "region_switching", "palette_breadth", "alternative_attempts"]),
    "M9": _t(
        slug="story_challenge", name="故事挑战", icon="📖", color="#3fae8a", difficulty=2,
        research_goal="ecological validity：受控任务里看到的行为模式，在真实创作里还在吗",
        time_limit_sec=900, allowed_tools=COLOR_TOOLS, prompt_style="story",
        rubric=_t(primary_dimensions=["imagination", "picture_organization"],
                  secondary_dimensions=["transformation", "color_richness", "line_combination"]),
        process_targets=["planning_latency", "new_element_count", "idea_shift",
                         "region_switching", "large_revision"]),
}


# ---------------------------------------------------------------------------
# Builders: prompt bank + cards -> concrete, stably-identified task rows
# ---------------------------------------------------------------------------
def _row(family: str, form_id: str, *, title: str, instruction: str,
         prompt_style: Optional[str] = None, stimulus: Optional[Dict[str, Any]] = None,
         condition: Optional[Dict[str, Any]] = None, hint: str = "",
         time_limit_sec: Optional[int] = None,
         allowed_tools: Optional[List[str]] = None,
         version: str = "", tiers: Optional[List[str]] = None, anchor: bool = False,
         legacy: bool = True) -> Dict[str, Any]:
    fam = FAMILIES[family]
    stim = stimulus or {"kind": "none"}
    task_id = f"{family}_{form_id}"
    return {
        "task_id": task_id, "id": task_id,          # `id` is the game-facing alias
        "family": family, "family_slug": fam["slug"], "family_name": fam["name"],
        "form_id": form_id, "version": version or LEGACY_VERSION,
        # v2.2：哪一版的孩子看到它（simple = 小学，full = 初中，两个都有 = 共通锚定题）；
        # legacy = v1 的题，留着给旧数据查 id，不再上地图
        "tiers": list(tiers or []), "anchor": bool(anchor), "legacy": bool(legacy),
        "prompt_style": prompt_style or fam["prompt_style"],
        "title": title, "instruction": instruction, "prompt": instruction,  # `prompt` = legacy alias
        "hint": hint,
        "stimulus": stim,
        # legacy reference block, so the existing UI/condition path keeps working
        "reference": ({"id": stim["stimulus_id"], "file": stim["file"], "mode": stim.get("mode", "always")}
                      if stim.get("kind") == "reference" else None),
        "time_limit_sec": time_limit_sec if time_limit_sec is not None else fam["time_limit_sec"],
        "allowed_tools": allowed_tools or fam["allowed_tools"],
        "phases": fam.get("phases"),
        "condition": dict(condition or {}),
        "rubric": fam["rubric"],
        "process_targets": list(fam["process_targets"]),
        "research_goal": fam["research_goal"],
        "category": fam["slug"], "difficulty": fam["difficulty"],
        "icon": fam["icon"], "color": fam["color"], "type": fam["name"],
        "enabled": True,
    }


LEGACY_VERSION = "1.0"     # v1 的 75 道：留在库里，不上地图
TASK_VERSION = "2.2"       # 现在孩子看到的题面（docs/任务库v2.2_双锚定题对齐版.md）


def _build_m1() -> List[Dict[str, Any]]:
    out = []
    for form, title, text in M1_PROMPTS:
        sid = f"m1_scene_{form.lower()}"
        out.append(_row("M1", form, title=title, instruction=text,
                        hint="先把大的结构和位置定下来，再补细节。",
                        stimulus=_reference(f"/static/refs/m1/{sid}.jpg", sid)))
    return out


def _build_m2() -> List[Dict[str, Any]]:
    # every form keeps the same visual load so the parallel forms stay comparable
    spec = {"objects": 4, "overlaps": 2, "size_difference": True, "depth": True,
            "example": "toy robot + plant + box + ball"}
    out = []
    for form, title, text in M2_PROMPTS:
        sid = f"m2_scene_{form.lower()}"
        stim = _reference(f"/static/refs/m2/{sid}.jpg", sid)
        stim["spec"] = spec
        out.append(_row("M2", form, title=title, instruction=text,
                        hint="注意谁在前面、谁被挡住、谁更大。", stimulus=stim))
    return out


def _build_m3() -> List[Dict[str, Any]]:
    out = []
    for i, (form, title, text) in enumerate(M3_PROMPTS):
        seed = "A" if i % 2 == 0 else "B"
        card = M3_NARRATIVE[i % len(M3_NARRATIVE)]
        out.append(_row("M3", form, title=title,
                        instruction=f"{text}\n\n另外，这幅画里：{card}",
                        hint="碎片可以旋转着看，也可以只用其中几个。",
                        stimulus=_fragments(seed),
                        condition={"fragment_seed": seed, "narrative_card": card}))
    return out


_M4_TEMPLATES = {
    "minimal": "把{base}改造成能在{env}使用的{goal}。",
    "story": "你被困在{env}，只有一个{base}。把它改造成能帮到你的{goal}。",
    "challenge": "把{base}改造成{env}里的{goal}，但必须还能看出它原来是{base}，而且至少要能服务两个生物。",
}


def _build_m4() -> List[Dict[str, Any]]:
    base_zh = {k: zh for k, _, zh in M4_BASE}
    base_ab = {k: ab for k, ab, _ in M4_BASE}
    env_zh = {k: zh for k, _, zh in M4_ENV}
    env_ab = {k: ab for k, ab, _ in M4_ENV}
    goal_zh = {k: zh for k, _, zh in M4_GOAL}
    goal_ab = {k: ab for k, ab, _ in M4_GOAL}
    out = []
    for base, env, goal in M4_COMBOS:
        for style, tmpl in _M4_TEMPLATES.items():
            form = f"{base_ab[base]}_{env_ab[env]}_{goal_ab[goal]}_{style}"
            text = tmpl.format(base=base_zh[base], env=env_zh[env], goal=goal_zh[goal])
            sid = f"m4_{base}"
            out.append(_row("M4", form, title=f"{base_zh[base]} → {goal_zh[goal]}",
                            instruction=text, prompt_style=style,
                            hint="想想它的哪一部分保留、哪一部分改变。",
                            stimulus=_reference(f"/static/refs/m4/{sid}.png", sid, "on_demand"),
                            condition={"base_object": base, "environment": env, "goal": goal}))
    return out


def _build_m5() -> List[Dict[str, Any]]:
    out = []
    for i, (a, b, a_zh, b_zh) in enumerate(M5_PAIRS):
        form_letter, title, text = M5_PROMPTS[i % len(M5_PROMPTS)]
        form = f"{a.upper()}_{b.upper()}_{form_letter}"
        out.append(_row("M5", form, title=f"{a_zh} + {b_zh}",
                        instruction=f"{text}\n\n这次要融合的是：{a_zh} 和 {b_zh}。",
                        hint="不是把两个放在一起，是让它们长成一个。",
                        condition={"concept_a": a, "concept_b": b}))
    return out


def _build_m6() -> List[Dict[str, Any]]:
    out = []
    for form, title, text, variants in M6_PROMPTS:
        sid = f"m6_scene_{form.lower()}"
        stim = _reference(f"/static/refs/m6/{sid}.jpg", sid)
        for variant in (variants or [None]):
            field = "mood" if form == "A" else "when"
            key, zh = variant if variant else (None, None)
            body = text.format(**{field: zh}) if key else text
            out.append(_row("M6", f"{form}_{key}" if key else form, title=title, instruction=body,
                            hint="同一种颜色也可以画深一点、淡一点。",
                            stimulus=stim, condition={field: key, f"{field}_zh": zh} if key else {}))
    return out


def _build_m7() -> List[Dict[str, Any]]:
    out = []
    for i, (concept, zh) in enumerate(M7_CONCEPTS):
        form_letter, title, text = M7_PROMPTS[i % len(M7_PROMPTS)]
        phase1 = FAMILIES["M7"]["phases"][0]
        out.append(_row("M7", f"{concept.upper()}_{form_letter}", title=title,
                        instruction=(f"第一步（{phase1['seconds']} 秒）：不要画任何具体东西，"
                                     f"只用线条表现「{zh}」。\n\n"
                                     f"第二步：不要删掉刚才的线条，{text}"),
                        hint="线的粗细、快慢、疏密都可以说话。",
                        condition={"concept": concept, "two_phase": True}))
    return out


def _build_m8() -> List[Dict[str, Any]]:
    out = []
    for form, refs in M8_SETS:
        rules = [M8_RULES[cat][int(idx)] for cat, idx in (r.split(":") for r in refs)]
        out.append(_row("M8", form, title="不可能世界",
                        instruction=("设计一个下面这些规则都成立的世界。"
                                     "画出这里的人或生物如何生活，以及正在发生什么。\n\n"
                                     + "\n".join(f"· {r}" for r in rules)),
                        hint="先决定这些规则会让生活变成什么样，再动笔。",
                        condition={"rules": rules, "rule_refs": refs}))
    return out


def _build_m9() -> List[Dict[str, Any]]:
    return [_row("M9", form, title=title, instruction=text,
                 hint="让画面里的东西替你讲故事。")
            for form, title, text in M9_PROMPTS]


M0_TASKS = [
    ("emotion_alone", "🌗", "画出「孤独」或「快乐」",
     "不要直接画一张脸或表情。用颜色、空间、物体和构图，让整张画面本身传达「孤独」或「快乐」中的一种感觉。",
     "想一想：这种感觉是大的还是小的？是空旷的还是拥挤的？是冷的还是暖的？",
     ["color_contrast", "picture_organization", "imagination"], "#e8632b"),
    ("imagine_animal", "🦄", "设计一种不存在的动物",
     "创造一种世界上没有的动物。它住在哪里？吃什么？有什么特别的本领？把它和它生活的地方画出来。",
     "可以把两三种你熟悉的动物或物体的特点组合起来，再改变大小和比例。",
     ["imagination", "deformation", "transformation"], "#7b4fd6"),
    ("transform_chair", "🪑", "一把椅子变成了……",
     "从一把普通的椅子出发，把它变成一个完全不同用途的东西——交通工具、生物、建筑、乐器，都可以。让人还能认出它曾经是一把椅子。",
     "先想它的哪一部分保留，哪一部分改变，再决定它的新功能。",
     ["transformation", "imagination", "line_combination"], "#2b7de8"),
    ("color_rain_city", "🌧️", "只用三种颜色画下雨的城市",
     "选择三种颜色（黑白不算），只用这三种颜色画一座下雨的城市。想办法让画面有远近、有明暗、有雨的感觉。",
     "同一种颜色可以画得深一点或淡一点，也可以叠加。",
     ["color_richness", "color_contrast", "picture_organization"], "#2e9e5b"),
    ("story_character_home", "🏠", "我的角色和它的家",
     "创造一个属于你的角色，并画出它的家。家里应该能看出这个角色喜欢什么、害怕什么、每天在做什么。",
     "角色可以很小，家可以很大；或者相反。让物品替角色讲故事。",
     ["picture_organization", "line_combination", "imagination"], "#d9455f"),
]


def _build_m0() -> List[Dict[str, Any]]:
    out = []
    for tid, icon, title, text, hint, dims, color in M0_TASKS:
        row = _row("M0", tid, title=title, instruction=text, hint=hint)
        # the original ids are preserved verbatim: they are foreign keys in data
        # that already exists
        row["task_id"] = row["id"] = tid
        row["form_id"] = tid
        row["icon"], row["color"] = icon, color
        row["rubric"] = {"primary_dimensions": list(dims)}
        out.append(row)
    return out


_BUILDERS = {"M0": _build_m0, "M1": _build_m1, "M2": _build_m2, "M3": _build_m3, "M4": _build_m4, "M5": _build_m5,
             "M6": _build_m6, "M7": _build_m7, "M8": _build_m8, "M9": _build_m9}


# ---------------------------------------------------------------------------
# v2.2：按年龄分两版（missions_v2.py 是题面唯一的家，这里只把它变成行）
# ---------------------------------------------------------------------------
def _build_v2() -> List[Dict[str, Any]]:
    from .missions_v2 import V2, M7_STEP1, M7_STEP2, M8_LEAD
    out = []
    for fam, forms in V2.items():
        for f in forms:
            common = dict(version=TASK_VERSION, tiers=f["tiers"], anchor=f["anchor"], legacy=False,
                          title=f["title"], hint=f.get("hint", ""))
            text = f["instruction"]
            stim, cond = None, {"tiers": list(f["tiers"]), "anchor": f["anchor"]}
            if fam in ("M1", "M2"):
                sid = f"{fam.lower()}_scene_{f['scene']}"
                stim = _reference(f"/static/refs/{fam.lower()}/{sid}.jpg", sid)
                if fam == "M2":
                    stim["spec"] = {"objects": 4, "overlaps": 2, "size_difference": True, "depth": True}
            elif fam == "M3":
                stim = _fragments(f["seed"]); cond["fragment_seed"] = f["seed"]
            elif fam == "M4":
                stim = _reference(f"/static/refs/m4/m4_{f['base']}.png", f"m4_{f['base']}", "on_demand")
                cond.update(base_object=f["base"], environment=f.get("env", ""), goal=f["goal"])
            elif fam == "M5":
                cond.update(concept_a=f["a"], concept_b=f["b"])
            elif fam == "M6":
                sid = f"m6_scene_{f['scene']}"
                stim = _reference(f"/static/refs/m6/{sid}.jpg", sid)
                cond["mood"] = f["mood"]
            elif fam == "M7":
                seconds = FAMILIES["M7"]["phases"][0]["seconds"]
                text = (M7_STEP1.format(seconds=seconds, text=f["instruction"]) + "\n\n"
                        + M7_STEP2.format(text=f["step2"]))
                cond.update(concept=f["concept"], two_phase=True)
            elif fam == "M8":
                rules = list(f["rules"])
                text = M8_LEAD + f["instruction"] + "\n\n" + "\n".join(f"· {r}" for r in rules)
                if f.get("challenge"):
                    text += f"\n挑战：{f['challenge']}"
                cond.update(rules=rules, challenge=f.get("challenge", ""))
            out.append(_row(fam, f["code"], instruction=text, stimulus=stim, condition=cond, **common))
    return out


def build_library() -> List[Dict[str, Any]]:
    """Every curated form, in family order. Ids are stable across runs.

    v2.2 rows first (what the map shows), then the v1 rows flagged `legacy`
    (ids that existing sessions point at)."""
    out: List[Dict[str, Any]] = list(_build_v2())
    for family in FAMILIES:
        out.extend(_BUILDERS[family]())
    return out
