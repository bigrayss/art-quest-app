# -*- coding: utf-8 -*-
"""材料规格与检查：材料是任务条件的一部分，不是附件。

「材料应该是什么」（`MATERIALS` 规格）与「实际材料是否满足」（`check_material`）分开（BrowserGym 的做法）。
每份材料先定用途——选题卡预览 / 正式观察参考 / 供改造的物品图 / 印在画布上的碎片——用途不混用。
开放题「无参考图」是明确配置（`NONE`），不是字段缺失。

视觉检查按依赖排（DSG 的改编）：对象存在 → 可辨识 → 关系成立 → 在实际显示尺寸下仍清楚。
结果只有四种：符合 / 不符合 / 无法判断 / 阻塞（前提失败）。没有视觉模型时需要看图的项一律「无法判断」，
并把实际显示帧裁出来给人看；**不用平均分把失败盖掉**。
能用像素量出来的东西（尺寸、白底、物体占高、饱和度、裁切损失）这里真的量。
"""
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
REFS = ROOT / "static" / "refs"

OK, FAIL, UNKNOWN, BLOCKED = "符合", "不符合", "无法判断", "阻塞"
NONE = {"kind": "none", "note": "开放题：明确不提供参考图（不是漏了字段）"}

# 实际显示帧（按 static/style.css 与 docs/ART_LIST.md 的显示规格，不另定通用分辨率）
#   thumb_desktop: 创作屏右栏缩略图 .ref-thumb 高 8rem、object-fit:cover → 约 2:1 的横条，裁上下
#   thumb_phone:   窄屏右栏更宽、高度不变 → 约 2.8:1，裁得更多
#   intent:        心愿页 .intent-ref object-fit:contain → 整图可见
#   modal:         点开的大图 .ref-viewport contain + 可放大 4×
FRAMES: Dict[str, Dict[str, Any]] = {
    "thumb_desktop": dict(aspect=2.0, fit="cover", note="右栏缩略图（约 512×256 设备像素）"),
    "thumb_phone": dict(aspect=2.8, fit="cover", note="手机竖屏时的缩略图"),
    "intent": dict(aspect=None, fit="contain", note="心愿页整图"),
    "modal": dict(aspect=None, fit="contain", zoom=4, note="点开看的大图，可放大 4 倍"),
}
CANVAS_W, CANVAS_H = 2048, 1408


def _scene(sid: str, purpose: str, objects: List[str], relations: List[str], presentation: str,
           must_not: Optional[List[str]] = None, variable: Optional[List[str]] = None, **extra: Any) -> Dict[str, Any]:
    return dict(id=sid, kind="reference", purpose=purpose, objects=objects, relations=relations,
                presentation=presentation, must_not=must_not or ["文字", "商标", "真人的脸"],
                variable=variable or ["材质", "细节", "风格（在同一套内）"], **extra)


MATERIALS: Dict[str, Dict[str, Any]] = {m["id"]: m for m in [
    # ---- M1：正式观察参考，常显；6–8 个物体、三层纵深 ----
    _scene("m1_scene_a", "正式观察参考（M1：整幅重现）", ["沙发", "猫（在沙发上）", "茶几", "书架", "台灯", "盆栽", "窗"],
           ["前中后三层可分", "物体边界清楚、不糊成一团", "白天、光线均匀", "没有人"], "扁平插画", count_range=(6, 8)),
    _scene("m1_scene_b", "正式观察参考（M1）", ["帐篷", "背包", "篝火", "树桩", "溪流", "远山", "树"],
           ["三层纵深", "地面看得见"], "扁平插画", count_range=(6, 8)),
    _scene("m1_scene_c", "正式观察参考（M1）", ["台灯", "地图", "放大镜", "书", "椅子", "挂钟", "软木板"],
           ["三层纵深", "桌上和墙上的东西都可辨识"], "扁平插画", count_range=(6, 8)),
    _scene("m1_scene_d", "正式观察参考（M1）", ["长椅", "滑梯", "秋千", "路灯", "树", "花"],
           ["三层纵深", "平视地面视角（不是俯拍）"], "扁平插画", count_range=(6, 8)),
    _scene("m1_scene_e", "正式观察参考（M1）", ["课桌椅", "黑板", "书架", "地球仪", "绿植", "窗", "讲台"],
           ["三层纵深"], "扁平插画", count_range=(6, 8)),
    # ---- M2：正好 4 物体、正好 2 遮挡、大小差、纵深 ----
    _scene("m2_scene_a", "正式观察参考（M2：大小 / 前后 / 遮挡）", ["玩具机器人", "绿植", "星星图案的盒子", "足球"],
           ["正好 2 处遮挡，一眼看得出", "有明显大小差", "有前后距离", "素色桌面和背景"], "扁平插画", count_exact=4, overlaps_exact=2),
    _scene("m2_scene_b", "正式观察参考（M2）", ["蓝水壶", "苹果", "绿书", "红玩具车"],
           ["正好 2 处遮挡", "大小差", "前后距离"], "扁平插画", count_exact=4, overlaps_exact=2),
    _scene("m2_scene_c", "正式观察参考（M2）", ["贝壳", "木质宝箱", "提灯", "绳圈"],
           ["正好 2 处遮挡", "大小差", "前后距离"], "扁平插画", count_exact=4, overlaps_exact=2),
    _scene("m2_scene_d", "正式观察参考（M2）", ["积木塔", "马克杯", "泰迪熊", "骰子"],
           ["正好 2 处遮挡", "大小差", "前后距离"], "扁平插画", count_exact=4, overlaps_exact=2),
    _scene("m2_scene_e", "正式观察参考（M2）", ["相机（后排左，最大）", "笔筒（后排右）", "折叠尺（前排右）", "橘子（前排，最小）"],
           ["折叠尺压住笔筒底部", "橘子挡住相机下缘", "相机最大、橘子最小"], "照片风（原图 1512×1040 放大到 2048×1408，比另四张略软）",
           count_exact=4, overlaps_exact=2, provenance="2026-10-03 到位；原图相机商标与笔筒英文已抹掉（只掩字本身 + 扩散填充）"),
    # ---- M4：供改造的物品图，默认收起 ----
    _scene("m4_umbrella", "供改造的物品参考（M4，on_demand）", ["撑开的雨伞"], ["纯白底", "伞面和伞柄可见", "占高约 75 %"], "扁平插画", white_bg=True, fill_range=(0.55, 0.9)),
    _scene("m4_backpack", "供改造的物品参考（M4）", ["背包"], ["纯白底", "轮廓完整不出框", "口袋、带子、拉链可见", "占高约 70 %"], "扁平插画", white_bg=True, fill_range=(0.55, 0.9)),
    _scene("m4_chair", "供改造的物品参考（M4）", ["四腿椅子"], ["纯白底", "四分之三侧视", "占高约 70 %"], "扁平插画", white_bg=True, fill_range=(0.55, 0.9)),
    _scene("m4_teapot", "供改造的物品参考（M4）", ["茶壶"], ["纯白底", "壶嘴、壶把、壶盖可见", "占高约 70 %"], "扁平插画", white_bg=True, fill_range=(0.55, 0.9)),
    _scene("m4_clock", "供改造的物品参考（M4）", ["闹钟 / 挂钟"], ["纯白底", "表盘刻度和指针清楚", "占高约 70 %"], "扁平插画", white_bg=True, fill_range=(0.55, 0.9)),
    _scene("m4_shoe", "供改造的物品参考（M4）", ["运动鞋"], ["纯白底", "鞋带、鞋底纹路可见", "占宽约 75 %"], "扁平插画", white_bg=True, fill_range=(0.55, 0.9), fill_axis="width"),
    _scene("m4_bicycle", "供改造的物品参考（M4）", ["自行车"], ["纯白底", "整车不出框", "车架、链条、两轮、车把、脚踏可见", "占高约 70 %"],
           "照片级渲染（和另六张扁平插画不是一套）", white_bg=True, fill_range=(0.55, 0.9)),
    # ---- M6：情绪中性、低饱和的场景，常显 ----
    _scene("m6_scene_a", "供改色的中性场景（M6，always）", ["小街 / 小院", "天空", "地面", "房子或树"],
           ["阴天或平光", "颜色偏灰偏淡、饱和度低", "没有人"], "扁平插画", neutral=True, sat_max=0.5),
    _scene("m6_scene_b", "供改色的中性场景（M6）", ["天空（占一半以上）", "田野或海边"], ["晴朗无云、平光", "低饱和"], "扁平插画", neutral=True, sat_max=0.5),
    _scene("m6_scene_c", "供改色的中性场景（M6）", ["河 / 路（中间分界）", "两边相似的内容"], ["左右基本对称、中间有自然分界", "平光"], "扁平插画", neutral=True, sat_max=0.5),
    _scene("m6_scene_d", "供改色的中性场景（M6）", ["一个明确的主角（小屋 / 船 / 独立的树）", "五六样次要的东西"], ["整体中性、低饱和"], "扁平插画", neutral=True, sat_max=0.5),
    _scene("m6_scene_e", "供改色的中性场景（M6）", ["几栋房子", "一条路", "几棵树", "天空"], ["白天平光、中性", "元素要够多"], "扁平插画", neutral=True, sat_max=0.5),
]}
# ---- 首访任务库（2026-10-12）的 15 张参考图：规格来自文档的「必要条件」；真图未到，先占位 ----
def _bank_specs() -> Dict[str, Dict[str, Any]]:
    import json as _json
    doc = _json.loads((ROOT / "artquest" / "bank" / "first_visit_v1.json").read_text("utf-8"))
    out = {}
    for t in doc["tasks"]:
        sid = t["reference"]
        if not sid:
            continue
        kind = {"OB": "正式观察参考（首访 OB）", "FG": "片段参考（首访 FG：转抄到空白画布，不印在画布上）", "TR": "供改造的物品参考（首访 TR）"}[t["family"]]
        if t["band"] == "B6":
            kind += "；第六段沿用本项目 M 族素材"
        size = None
        try:
            from PIL import Image
            fp = file_of(sid)
            with Image.open(fp) as im:
                size = im.size
        except Exception:
            pass
        out[sid] = dict(id=sid, kind="reference", purpose=kind, objects=[t["zh"]["requirements"]],
                        relations=["题面点名的对象 / 关系在图里清楚", "contain 完整显示下仍清楚"],
                        presentation=("插画版（从展示拼版精确裁出，原生 %d×%d，非 1600×1200）" % size if size and size != (1600, 1200) else "PNG 1600×1200（原样保留的旧素材）"),
                        must_not=["文字", "商标", "真人的脸", "改造答案（TR）"], variable=["风格"], size=size or (1600, 1200),
                        status="真图（docs/Phase0_实际展示参考图_核对重打包_v3.zip，2026-10-12）",
                        provenance="01 插画版 / 03 原样保留；02 写实版 5 张在 refs/bank/alt_photoreal/ 不混用")
    return out
MATERIALS.update(_bank_specs())
for _seed in "ABCDE":
    MATERIALS[f"m3_fragments_{_seed.lower()}"] = dict(
        id=f"m3_fragments_{_seed.lower()}", kind="fragments", purpose="印在初始画布上的碎片（M3）",
        objects=["弧", "两个点", "线", "角", "曲线", "缺口矩形"], relations=["七块、元件种类同 A/B，只是摆法不同", "擦不掉（橡皮擦回初始画布）"],
        presentation="矢量（artquest/reconstruct.draw_stimulus 与 static/app.js:drawStimulus 同一实现）",
        must_not=["位图"], variable=["摆法"])


def file_of(sid: str) -> Optional[Path]:
    fam = sid.split("_", 1)[0]
    for ext in (".jpg", ".png", ".jpeg"):
        p = REFS / fam / f"{sid}{ext}"
        if p.exists():
            return p
    for ext in (".png", ".jpg"):               # 首访任务库的图都在 refs/bank/（B6_OB 是 jpg）
        p = REFS / "bank" / f"{sid}{ext}"
        if p.exists():
            return p
    return None


def questions(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """DSG 式的依赖问题：对象 → 可辨识 → 关系 → 显示尺寸下仍清楚。每题带 `requires`（前提题 id）。"""
    qs: List[Dict[str, Any]] = []
    if spec["kind"] != "reference":
        return qs
    for i, obj in enumerate(spec["objects"]):
        qs.append(dict(id=f"obj{i}", q=f"图中是否存在「{obj}」？", requires=[], needs_vision=True))
        qs.append(dict(id=f"rec{i}", q=f"「{obj}」是否能一眼辨识？", requires=[f"obj{i}"], needs_vision=True))
    if spec.get("count_exact"):
        qs.append(dict(id="count", q=f"图中是否**只有** {spec['count_exact']} 个物体（无额外、无重复、无被裁切到难以判断的）？",
                       requires=[f"obj{i}" for i in range(len(spec["objects"]))], needs_vision=True))
    for j, rel in enumerate(spec["relations"]):
        qs.append(dict(id=f"rel{j}", q=f"关系是否成立：{rel}？", requires=[f"rec{i}" for i in range(len(spec["objects"]))], needs_vision=True))
    for fid in ("thumb_desktop", "thumb_phone"):
        qs.append(dict(id=f"frame_{fid}", q=f"在 {FRAMES[fid]['note']} 裁切后，关键对象与关系是否仍清楚？",
                       requires=[f"rel{j}" for j in range(len(spec["relations"]))], needs_vision=True))
    return qs


# ---- 像素级能量的条件 ----------------------------------------------------------
def _measure(path: Path) -> Dict[str, Any]:
    from PIL import Image, ImageStat
    im = Image.open(path).convert("RGB")
    w, h = im.size
    small = im.resize((256, int(256 * h / w)))
    hsv = small.convert("HSV")
    sat = ImageStat.Stat(hsv.getchannel("S")).mean[0] / 255.0
    # 白底 + 物体占高：近白像素（RGB 都 ≥ 245）当背景
    px = small.load()
    ys, xs, corners_white = [], [], 0
    for y in range(small.size[1]):
        for x in range(small.size[0]):
            r, g, b = px[x, y]
            if not (r >= 245 and g >= 245 and b >= 245):
                ys.append(y); xs.append(x)
    for cx, cy in ((0, 0), (small.size[0] - 1, 0), (0, small.size[1] - 1), (small.size[0] - 1, small.size[1] - 1)):
        r, g, b = px[cx, cy]
        corners_white += int(r >= 245 and g >= 245 and b >= 245)
    fill = (max(ys) - min(ys) + 1) / small.size[1] if ys else 0.0
    fill_w = (max(xs) - min(xs) + 1) / small.size[0] if xs else 0.0
    return dict(width=w, height=h, format=im.format or path.suffix, saturation=round(sat, 3),
                corners_white=corners_white, fill_height=round(fill, 3), fill_width=round(fill_w, 3))


def crop_box(w: int, h: int, aspect: float):
    """object-fit: cover 的中心裁切框。"""
    target_h = int(round(w / aspect))
    if target_h <= h:
        top = (h - target_h) // 2
        return (0, top, w, top + target_h)
    target_w = int(round(h * aspect))
    left = (w - target_w) // 2
    return (left, 0, left + target_w, h)


# 人工核过的结论（2026-10-12，v3 包逐张和题面对照；谁看的、看到什么都写在 note 里）。
# 这不是模型判断，是研究者的眼睛；有了视觉模型也不覆盖它，两者并列记。
HUMAN_NOTES: Dict[str, tuple] = {
    "B1_OB_ref": (OK, "两片叶子：左宽（绿、圆）右长（黄、尖），叶柄叶脉清楚，和题面一致"),
    "B2_OB_ref": (OK, "苹果和两本书，苹果挡住下面那本；题面 1.0.1 已按图改成「苹果和两本书」"),
    "B3_OB_ref": (OK, "盆栽、笔筒、橡皮、笔记本，橡皮在盆栽前、笔记本在笔筒前；题面 1.0.1 已按图改"),
    "B4_OB_ref": (OK, "窗边的花瓶、花和两本书；题面 1.0.1 已按图改成「花瓶、花和书」"),
    "B5_OB_ref": (OK, "街角：建筑转角两个面、路灯、人行道、道路延伸方向都在，和题面一致"),
    "B1_TR_ref": (OK, "蓝色马克杯，特征清楚"), "B2_TR_ref": (OK, "展开的黄色雨伞（写实版那张是收拢的，没用）"),
    "B3_TR_ref": (OK, "茶壶（CSV：蓝白茶壶）"), "B4_TR_ref": (OK, "蓝色自行车，整车在框内"), "B5_TR_ref": (OK, "台灯（CSV：绿色台灯）"),
    "B1_FG_ref": (OK, "旧素材原样保留，1600×1200"), "B2_FG_ref": (OK, "同上"), "B3_FG_ref": (OK, "三段线条，和题面「三段线条」一致"),
    "B4_FG_ref": (OK, "同上，四段"), "B5_FG_ref": (OK, "同上，四段"),
    # 第六段（17 岁及以上）：沿用本项目素材（2026-10-12）
    "B6_OB_ref": (OK, "M1 客厅场景 m1_scene_a：沙发（有猫）、茶几、书架、台灯、盆栽、窗，三层纵深，和题面一致"),
    "B6_FG_ref": (OK, "M3 碎片组 E 渲染成 1600×1200：七块（弧、两点、线、角、曲线、缺口矩形）"),
    "B6_TR_ref": (OK, "M4 鞋子 m4_shoe：运动鞋侧视，鞋带鞋底可见"),
}


def check_material(sid: str, judge: Optional[Callable[[Path, str], str]] = None) -> Dict[str, Any]:
    """一份材料的检查结果。`judge(path, question) -> 符合|不符合|无法判断` 是可插拔的视觉判断；
    没有就把需要看图的项记成「无法判断」，前提失败的项记「阻塞」。"""
    spec = MATERIALS.get(sid)
    if spec is None:
        from .drafts import DRAFT_MATERIALS
        spec = DRAFT_MATERIALS.get(sid)
    items: List[Dict[str, Any]] = []
    if spec is None:
        return dict(id=sid, status=FAIL, items=[dict(id="spec", status=FAIL, note="没有材料规格")])
    if spec["kind"] == "fragments":
        from ..missions import _fragments
        n = len(_fragments(sid[-1].upper())["items"])
        items.append(dict(id="count", status=OK if n == 7 else FAIL, note=f"{n} 块矢量元件"))
        return dict(id=sid, status=_overall(items), items=items, spec=spec)

    path = file_of(sid)
    if path is None:
        items.append(dict(id="file", status=FAIL, note="文件不存在" + ("（草案材料：待制作）" if spec.get("status") == "待制作" else "")))
        return dict(id=sid, status=FAIL, items=items, spec=spec)
    m = _measure(path)
    items.append(dict(id="file", status=OK, note=str(path.relative_to(ROOT))))
    want = tuple(spec.get("size") or (CANVAS_W, CANVAS_H))
    items.append(dict(id="size", status=OK if (m["width"], m["height"]) == want else FAIL,
                      note=f"{m['width']}×{m['height']}（规格 {want[0]}×{want[1]}）"))
    try:
        import json
        placeholders = json.loads((REFS / "manifest.json").read_text("utf-8")).get("placeholders", [])
    except Exception:
        placeholders = []
    items.append(dict(id="placeholder", status=FAIL if sid in placeholders else OK, note="manifest.placeholders"))
    if spec.get("white_bg"):
        items.append(dict(id="white_bg", status=OK if m["corners_white"] == 4 else FAIL, note=f"四角近白 {m['corners_white']}/4"))
        lo, hi = spec["fill_range"]
        axis = spec.get("fill_axis", "height")
        val = m["fill_width"] if axis == "width" else m["fill_height"]
        items.append(dict(id="fill", status=OK if lo <= val <= hi else FAIL,
                          note=f"非白像素占{'宽' if axis == 'width' else '高'} {val:.0%}（规格 {lo:.0%}–{hi:.0%}；超出上限的在 2:1 缩略图里会被裁掉）"))
    if spec.get("neutral"):
        items.append(dict(id="saturation", status=OK if m["saturation"] <= spec["sat_max"] else FAIL,
                          note=f"平均饱和度 {m['saturation']:.2f}（上限 {spec['sat_max']}）"))
    # 显示帧：裁切损失是能算的；裁完关键对象还在不在要看图
    for fid, fr in FRAMES.items():
        if fr["fit"] == "cover":
            box = crop_box(m["width"], m["height"], fr["aspect"])
            lost = 1 - (box[3] - box[1]) * (box[2] - box[0]) / (m["width"] * m["height"])
            items.append(dict(id=f"crop_{fid}", status=OK, note=f"{fr['note']}：中心裁切保留 {1 - lost:.0%}，上下各去 {lost / 2:.0%}", box=box))
    if sid in HUMAN_NOTES:
        st, note = HUMAN_NOTES[sid]
        items.append(dict(id="human", status=st, note=f"人工核对（2026-10-12）：{note}", judge="human"))
    # 依赖式视觉问题
    answers: Dict[str, str] = {}
    for q in questions(spec):
        if any(answers.get(r) != OK for r in q["requires"]):
            st = BLOCKED
        elif judge is None:
            st = UNKNOWN
        else:
            st = judge(path, q["q"])
        answers[q["id"]] = st
        items.append(dict(id=q["id"], status=st, note=q["q"], requires=q["requires"]))
    return dict(id=sid, status=_overall(items), items=items, spec=spec, measured=m)


def _overall(items: List[Dict[str, Any]]) -> str:
    st = {i["status"] for i in items}
    if FAIL in st:
        return FAIL
    if UNKNOWN in st or BLOCKED in st:
        return UNKNOWN
    return OK


def render_frames(out_dir: Path, sids: Optional[List[str]] = None) -> List[Path]:
    """把实际显示帧裁出来给人看——检查的是孩子看到的那一帧，不是原始大图。"""
    from PIL import Image
    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for sid in (sids or [s for s, m in MATERIALS.items() if m["kind"] == "reference"]):
        path = file_of(sid)
        if path is None:
            continue
        im = Image.open(path).convert("RGB")
        for fid, fr in FRAMES.items():
            if fr["fit"] != "cover":
                continue
            box = crop_box(*im.size, fr["aspect"])
            crop = im.crop(box)
            crop.thumbnail((640, 640))
            p = out_dir / f"{sid}__{fid}.jpg"
            crop.save(p, quality=80)
            written.append(p)
    return written
