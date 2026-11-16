"""课堂模块：一节课 = 课件 + 课堂练习 + 课后作业；老师建班、学生凭班级码加入。

三样东西都在这一个文件里：

  * **课**（`LESSONS`）——内置的小课件和配套的画画任务。课件的文字和示意图都是自己写、自己画的：
    只对齐教材的**课题**，不抄教材的原文和图片。
  * **任务**——课堂练习和课后作业是和任务库里一样形状的任务，登记进 `QUESTS_BY_ID`（**不进** `QUESTS`：
    地图、选题、研究协议遍历的是那张表，课堂任务不该出现在那些地方）。所以建 session、打分、反馈、
    过程数据全部走原来的路，课堂上画的和平时画的是同一种数据。
  * **班级**（`data/classroom/`）——班级码、成员、老师上传的课件。作品不存在这里：一张课堂作品就是
    一条普通的 session，`routing.classroom = {class_code, lesson_id, task_kind}` 说它是哪个班哪节课的。

课有两种来源：`LESSONS` 里内置的样板课，和老师自己在界面上录入的课（`data/classroom/lessons/<id>.json`）。
老师的课可以从空白写起，也可以把样板课复制一份来改。两种课对外是同一个形状（`get_lesson`）。
"""
import copy
import json
import re
import secrets
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config
from .storage import now_iso
from .quests import QUESTS_BY_ID

ROOT = config.DATA_DIR / "classroom"
CLASSES_DIR = ROOT / "classes"
FILES_DIR = ROOT / "files"
LESSONS_DIR = ROOT / "lessons"            # 老师录入的课
LESSON_FILES_DIR = ROOT / "lesson_files"  # 课里的配图和附件
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
# 一节课的上限：够一堂课用，又不至于被塞成一本书
MAX_SLIDES, MAX_LINES, MAX_TASKS = 40, 8, 8
_LOCK = threading.Lock()

# 班级码要能念、能抄在黑板上：去掉 0/O、1/I/L 这些分不清的
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LEN = 6
MAX_UPLOAD_BYTES = 40 * 1024 * 1024
# 浏览器里能直接翻的（PDF、图片）和只能下载的（PPT）
UPLOAD_TYPES = {
    ".pdf": ("application/pdf", True), ".png": ("image/png", True), ".jpg": ("image/jpeg", True),
    ".jpeg": ("image/jpeg", True), ".webp": ("image/webp", True),
    ".ppt": ("application/vnd.ms-powerpoint", False),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", False),
}

# ---------------------------------------------------------------------------
#  示意图：自己画的线稿，跟着文字颜色走
# ---------------------------------------------------------------------------
_SVG = ('<svg viewBox="0 0 320 150" fill="none" stroke="currentColor" stroke-width="3" '
        'stroke-linecap="round" stroke-linejoin="round" role="img" aria-label="{label}">{body}</svg>')
_WATER = '<path d="M10 132q15-8 30 0t30 0 30 0 30 0 30 0 30 0 30 0 30 0 30 0 30 0" stroke-width="2" opacity=".5"/>'


def _fig(label: str, body: str) -> str:
    return _SVG.format(label=label, body=body + _WATER)


FIGURES = {
    "beam": _fig("梁桥", '<path d="M14 62h292M14 74h292"/><path d="M70 74v52M82 74v52M154 74v52M166 74v52M238 74v52M250 74v52"/>'
                 '<path d="M14 50h292" stroke-width="2"/><path d="M30 50v12M60 50v12M90 50v12M120 50v12M150 50v12M180 50v12M210 50v12M240 50v12M270 50v12M300 50v12" stroke-width="2"/>'),
    "arch": _fig("拱桥", '<path d="M14 96C80 40 240 40 306 96"/><path d="M14 112h36M270 112h36"/>'
                 '<path d="M50 126c0-52 40-74 110-74s110 22 110 74"/>'
                 '<path d="M40 84C100 34 220 34 280 84" stroke-width="2"/>'),
    "arch3": _fig("三孔拱桥", '<path d="M12 104C70 52 250 52 308 104"/>'
                  '<path d="M52 126c0-26 12-38 30-38s30 12 30 38M122 126c0-44 16-60 38-60s38 16 38 60M208 126c0-26 12-38 30-38s30 12 30 38"/>'),
    "covered": _fig("廊桥", '<path d="M30 126c20-50 60-64 130-64s110 14 130 64"/><path d="M40 80h240"/>'
                    '<path d="M52 80V46M92 80V40M132 80V38M188 80V38M228 80V40M268 80V46"/>'
                    '<path d="M28 50C90 30 230 30 292 50"/><path d="M40 38C100 14 220 14 280 38"/><path d="M28 50l12-12M292 50l-12-12"/>'),
    "cable": _fig("斜拉桥", '<path d="M10 92h300M10 102h300"/><path d="M110 126V18M210 126V18"/>'
                  '<path d="M110 22L30 92M110 34L52 92M110 46L74 92M110 22l44 70M110 34l30 58M210 22l80 70M210 34l58 58M210 46l36 46M210 22l-44 70M210 34l-30 58" stroke-width="2"/>'),
    "parts": _fig("桥的组成", '<path d="M14 96C80 40 240 40 306 96"/><path d="M50 126c0-52 40-74 110-74s110 22 110 74"/>'
                  '<path d="M40 84C100 34 220 34 280 84" stroke-width="2"/>'
                  '<g stroke-width="1.6"><path d="M160 30v-14M96 56L70 22M160 96v-24M286 98l14-22"/></g>'
                  '<g fill="currentColor" stroke="none" font-size="13" font-family="sans-serif">'
                  '<text x="146" y="12">栏杆</text><text x="46" y="18">桥面</text><text x="146" y="110">桥孔</text><text x="286" y="72">桥台</text></g>'),
    "depth": _fig("近大远小", '<path d="M8 120L250 44"/><path d="M8 84L250 36"/>'
                  '<path d="M8 84v36M56 74v31M100 66v26M140 58v21M176 51v17M206 45v13M230 40v10M250 36v8"/>'
                  '<path d="M256 34h56" stroke-width="2" opacity=".5"/><path d="M270 34c4-10 14-10 18 0M292 34c3-7 10-7 13 0" stroke-width="2" opacity=".5"/>'),
    "lines": _fig("线条的疏密", '<g stroke-width="2"><path d="M20 30h80M20 44h80M20 58h80M20 72h80"/>'
                  '<path d="M124 30h80M124 37h80M124 44h80M124 51h80M124 58h80M124 65h80M124 72h80"/>'
                  '<path d="M228 30h72v42h-72zM228 44h72M228 58h72M252 30v14M276 44v14M246 58v14M282 58v14M264 30v14"/></g>'
                  '<g fill="currentColor" stroke="none" font-size="13" font-family="sans-serif">'
                  '<text x="48" y="98">疏</text><text x="152" y="98">密</text><text x="244" y="98">石缝</text></g>'),
}

# ---------------------------------------------------------------------------
#  课
# ---------------------------------------------------------------------------
LESSONS: List[Dict[str, Any]] = [
    {
        "id": "zj5a_bridge",
        "title": "家乡的桥",
        "grade": 5,
        "subject": "美术 · 造型表现",
        "minutes": 40,
        # 课题对齐的是教材目录；目录来自第三方整理的电子课本网，没有官方核对——进课堂前请老师对一下课本
        "textbook": {"edition": "浙人美版 五年级上册（2026 年秋）", "lesson": "第 5 课", "verified": False},
        "summary": "认识桥的样子和结构，用线条画一座有远近的桥。",
        "objectives": [
            "说得出桥的几种样子：梁桥、拱桥、廊桥、斜拉桥。",
            "看得出一座桥由哪几部分组成。",
            "会用近大远小和线条的疏密，画出一座有远近的桥。",
        ],
        "slides": [
            {"title": "家乡的桥", "kind": "cover", "figure": "arch3",
             "lines": ["有河的地方就有桥。", "今天我们看桥、认桥，再画一座桥。"]},
            {"title": "杭州的桥", "figure": "arch3",
             "lines": ["拱宸桥：在京杭大运河的南端，是一座三个桥孔的石拱桥。",
                       "断桥：在西湖白堤的东头，只有一个桥孔。",
                       "钱塘江大桥：1937 年建成，茅以升主持修建，上层走汽车，下层走火车。"],
             "ask": "你家附近、上学路上有什么桥？它是什么样子的？"},
            {"title": "桥有哪几种样子", "figures": ["beam", "arch", "covered", "cable"],
             "captions": ["梁桥：桥面是平的，架在桥墩上", "拱桥：桥身弯成一道拱", "廊桥：桥上盖着长廊，能遮风挡雨", "斜拉桥：高高的桥塔用拉索拉住桥面"],
             "lines": ["河北的赵州桥是拱桥，隋朝的工匠李春建的，一千四百多年了还在用。",
                       "浙江南部的泰顺、庆元有很多木头搭的廊桥。"]},
            {"title": "一座桥由哪几部分组成", "figure": "parts",
             "lines": ["桥面：人和车走的地方。", "桥孔和桥墩：把桥撑起来，让水和船从下面过。",
                       "栏杆：护着桥上的人。", "桥台：桥的两头，和岸接在一起。"],
             "ask": "看图说一说：这座桥的桥面、桥孔、栏杆各在哪里？"},
            {"title": "怎么看一座桥", "figure": "arch",
             "lines": ["第一步，看大形：整座桥是平的，还是拱起来的？",
                       "第二步，看结构：有几个桥孔？桥墩在哪里？",
                       "第三步，看细节：栏杆、石缝、桥上的灯和人。"],
             "ask": "画的时候也按这个顺序：先大形，再结构，最后细节。"},
            {"title": "让桥有远近", "figure": "depth",
             "lines": ["近大远小：离我们近的栏杆高而宽，越远越矮、越密。",
                       "近处画清楚，远处画简单。",
                       "让桥从画面的一角斜着伸出去，比横着摆更有远近。"],
             "ask": "图里的栏杆哪一根最高？哪一根最矮？为什么？"},
            {"title": "线条的本事", "figure": "lines",
             "lines": ["线有粗细、长短、疏密。", "线画得密，那一块就显得暗；画得疏，就显得亮。",
                       "石头用短线，水面用长长的曲线，倒影用断开的横线。"]},
            {"title": "动手画", "kind": "tasks",
             "lines": ["课堂练习：先画一座桥的样子，再画一座有远近的桥。", "课后作业：画你家乡的一座桥。"]},
        ],
        "tasks": [
            {"key": "p1", "kind": "practice", "minutes": 10, "title": "桥的样子",
             "instruction": "从梁桥、拱桥、廊桥、斜拉桥里选一种，用线条画出它的样子。只用线，不涂色。",
             "requirements": "看得出是哪一种桥；画出桥面、桥墩或桥孔、栏杆。",
             "hint": "先画大形，再画结构，最后画细节。"},
            {"key": "p2", "kind": "practice", "minutes": 15, "title": "一座有远近的桥",
             "instruction": "画一座从近处伸向远处的桥。近处大而清楚，远处小而简单，再画上水面或倒影。",
             "requirements": "近处的栏杆比远处的高；桥下有水。",
             "hint": "让桥从画面的一角斜着伸出去。"},
            {"key": "h1", "kind": "homework", "minutes": 30, "title": "我家乡的桥",
             "instruction": "画一座你见过的桥：家附近的、上学路上的、旅行时见到的都可以。把桥周围也画出来——水、岸、树、房子、桥上的人。",
             "requirements": "桥是画面里最主要的；用上疏密不同的线；桥周围至少画两样东西。",
             "hint": "想一想你是站在哪里看这座桥的。"},
            {"key": "h2", "kind": "homework", "optional": True, "minutes": 30, "title": "未来的桥",
             "instruction": "设计一座还没有人造出来的桥。它架在哪里？给谁走？有什么特别的本事？",
             "requirements": "看得出它是一座桥；看得出它特别在哪里。",
             "hint": "可以从今天认识的四种桥里挑一种来改。"},
        ],
    },
]
LESSONS_BY_ID = {l["id"]: l for l in LESSONS}
KIND_NAMES = {"practice": "课堂练习", "homework": "课后作业"}
_TEMPLATE_ID = "M0_A1"      # 开放创作：九维都看、没有印好的图形、不限工具——课堂任务从它的形状长出来


def task_id(lesson_id: str, key: str) -> str:
    return f"CL_{lesson_id}_{key}"


def _quest(lesson: Dict[str, Any], t: Dict[str, Any]) -> Dict[str, Any]:
    q = copy.deepcopy(QUESTS_BY_ID[_TEMPLATE_ID])
    tid = task_id(lesson["id"], t["key"])
    text = t["instruction"] + (f" 要做到：{t['requirements']}" if t.get("requirements") else "")
    q.update({
        "id": tid, "task_id": tid, "form_id": t["key"],
        "family": "CL", "family_slug": "classroom", "family_name": "课堂", "category": "classroom",
        "type": KIND_NAMES[t["kind"]], "title": t["title"], "instruction": text, "prompt": text,
        "hint": t.get("hint", ""), "anchor": False, "legacy": False,
        "research_goal": f"课堂任务：{lesson['title']} / {KIND_NAMES[t['kind']]}",
        "classroom": {"lesson_id": lesson["id"], "kind": t["kind"], "key": t["key"]},
    })
    q["condition"] = dict(q.get("condition") or {}, anchor=False)
    return q


def register_lesson(lesson: Dict[str, Any]) -> List[str]:
    """把一节课的任务登记成任务库认得的任务；这节课里删掉的任务一并撤下。"""
    if _TEMPLATE_ID not in QUESTS_BY_ID:
        return []
    prefix, ids = f"CL_{lesson['id']}_", []
    for t in lesson.get("tasks") or []:
        q = _quest(lesson, t)
        QUESTS_BY_ID[q["id"]] = q
        ids.append(q["id"])
    for tid in [k for k in QUESTS_BY_ID if k.startswith(prefix) and k not in ids]:
        del QUESTS_BY_ID[tid]
    return ids


def register() -> List[str]:
    """内置的课和老师录入的课，全部登记。模板不在（任务库被换掉了）就什么都不登记。"""
    ids: List[str] = []
    for lesson in LESSONS + custom_lessons(None):
        ids += register_lesson(lesson)
    return ids


# ---------------------------------------------------------------------------
#  老师录入的课
# ---------------------------------------------------------------------------
def _lesson_path(lesson_id: str) -> Path:
    return LESSONS_DIR / f"{lesson_id}.json"


def is_custom_id(lesson_id: str) -> bool:
    return bool(re.fullmatch(r"t[0-9a-f]{10}", str(lesson_id or "")))


def get_lesson(lesson_id: str) -> Optional[Dict[str, Any]]:
    if lesson_id in LESSONS_BY_ID:
        return LESSONS_BY_ID[lesson_id]
    if not is_custom_id(lesson_id) or not _lesson_path(lesson_id).exists():
        return None
    try:
        return json.loads(_lesson_path(lesson_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def custom_lessons(owner_id: Optional[str]) -> List[Dict[str, Any]]:
    """`None` = 所有老师的。"""
    if not LESSONS_DIR.exists():
        return []
    rows = [get_lesson(p.stem) for p in sorted(LESSONS_DIR.glob("*.json"))]
    rows = [l for l in rows if l and (owner_id is None or l.get("owner_id") == owner_id)]
    return sorted(rows, key=lambda l: l.get("created_at") or "")


def _text(v: Any, n: int) -> str:
    return re.sub(r"[\x00-\x08\x0b-\x1f]", "", str(v or "")).strip()[:n]


def _clean_lesson(data: Dict[str, Any], old: Dict[str, Any]) -> Dict[str, Any]:
    """老师交上来的一节课，收拾成存盘的样子。`id`、归属、任务的 key 以存着的那份为准。"""
    title = _text(data.get("title"), 60)
    if not title:
        raise ValueError("请写上课题")
    files = {f["id"]: f for f in old.get("files") or []}
    slides = []
    for sl in (data.get("slides") or [])[:MAX_SLIDES]:
        lines = [_text(x, 200) for x in (sl.get("lines") or [])]
        row = {"title": _text(sl.get("title"), 60), "lines": [x for x in lines if x][:MAX_LINES], "ask": _text(sl.get("ask"), 200)}
        img = str(sl.get("image") or "")
        if img in files and files[img]["ext"] in IMAGE_EXTS:
            row["image"] = img
        # 从样板课复制来的示意图：只认内置的那几张
        figs = [n for n in (sl.get("figure_names") or []) if n in FIGURES][:4]
        if figs:
            row["figures"] = figs
            caps = [_text(c, 60) for c in (sl.get("captions") or [])][:len(figs)]
            if any(caps):
                row["captions"] = caps
        if sl.get("kind") in ("cover", "tasks"):
            row["kind"] = sl["kind"]
        if row["title"] or row["lines"] or row.get("image") or figs:
            slides.append(row)
    used = {t["key"] for t in old.get("tasks") or []}
    n, tasks = 0, []
    for t in (data.get("tasks") or [])[:MAX_TASKS]:
        name, what = _text(t.get("title"), 40), _text(t.get("instruction"), 400)
        if not name and not what:
            continue
        if not name or not what:
            raise ValueError("每个任务都要有题目，也要写清楚画什么")
        key = str(t.get("key") or "")
        if key not in used or any(x["key"] == key for x in tasks):   # 新任务：发一个没用过的 key
            while True:
                n += 1
                key = f"t{n}"
                if key not in used and not any(x["key"] == key for x in tasks):
                    break
        try:
            minutes = max(1, min(240, int(t.get("minutes") or 15)))
        except (TypeError, ValueError):
            minutes = 15
        tasks.append({"key": key, "kind": "homework" if t.get("kind") == "homework" else "practice",
                      "title": name, "instruction": what, "requirements": _text(t.get("requirements"), 200),
                      "hint": _text(t.get("hint"), 120), "minutes": minutes, "optional": bool(t.get("optional"))})
    try:
        minutes = max(5, min(240, int(data.get("minutes") or 40)))
    except (TypeError, ValueError):
        minutes = 40
    return dict(old, title=title, subject=_text(data.get("subject"), 40), summary=_text(data.get("summary"), 200),
                minutes=minutes, objectives=[x for x in (_text(o, 120) for o in (data.get("objectives") or [])) if x][:6],
                slides=slides, tasks=tasks, updated_at=now_iso())


def _write_lesson(lesson: Dict[str, Any]) -> Dict[str, Any]:
    LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _lesson_path(lesson["id"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(lesson, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_lesson_path(lesson["id"]))
    register_lesson(lesson)
    return lesson


def new_lesson(owner_id: str, owner_name: str, copy_of: str = "") -> Dict[str, Any]:
    """开一节新课：空白的，或者把一节现成的课（样板课、自己的课）复制一份来改。"""
    src = get_lesson(copy_of) if copy_of else None
    if copy_of and (not src or (src.get("owner_id") and src["owner_id"] != owner_id)):
        raise KeyError(copy_of)
    lesson = {"id": "t" + secrets.token_hex(5), "owner_id": owner_id, "owner_name": owner_name, "grade": None,
              "created_at": now_iso(), "updated_at": now_iso(), "copied_from": copy_of or "", "files": [],
              "title": "未命名的课", "subject": "", "summary": "", "minutes": 40, "objectives": [], "slides": [], "tasks": []}
    if src:
        lesson.update(title=src["title"], subject=src.get("subject", ""), summary=src.get("summary", ""),
                      minutes=src.get("minutes", 40), objectives=list(src.get("objectives") or []), grade=src.get("grade"),
                      tasks=[{k: t.get(k, d) for k, d in (("key", ""), ("kind", "practice"), ("title", ""), ("instruction", ""),
                                                           ("requirements", ""), ("hint", ""), ("minutes", 15), ("optional", False))}
                             for t in src["tasks"]])
        slides = []
        for sl in src["slides"]:
            row = {"title": sl.get("title", ""), "lines": list(sl.get("lines") or []), "ask": sl.get("ask", "")}
            names = sl.get("figures") or ([sl["figure"]] if sl.get("figure") else [])
            if names:
                row["figures"] = list(names)
            if sl.get("captions"):
                row["captions"] = list(sl["captions"])
            if sl.get("kind"):
                row["kind"] = sl["kind"]
            slides.append(row)                 # 别人课里的配图不跟着走：文件是那节课的
        lesson["slides"] = slides
    with _LOCK:
        return _write_lesson(lesson)


def save_lesson(lesson_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    with _LOCK:
        old = get_lesson(lesson_id)
        if not old or not is_custom_id(lesson_id):
            raise KeyError(lesson_id)
        return _write_lesson(_clean_lesson(data, old))


def delete_lesson(lesson_id: str) -> bool:
    """删一节课。已经画出来的作品不受影响：每条 session 里冻着当时的题面。"""
    with _LOCK:
        if not is_custom_id(lesson_id) or not _lesson_path(lesson_id).exists():
            return False
        _lesson_path(lesson_id).unlink()
        for tid in [k for k in QUESTS_BY_ID if k.startswith(f"CL_{lesson_id}_")]:
            del QUESTS_BY_ID[tid]
        d = LESSON_FILES_DIR / lesson_id
        if d.exists():
            for f in d.iterdir():
                f.unlink()
            d.rmdir()
        for p in (CLASSES_DIR.glob("*.json") if CLASSES_DIR.exists() else []):
            cls = load(p.stem)
            if cls and lesson_id in cls.get("lesson_ids", []):
                cls["lesson_ids"] = [x for x in cls["lesson_ids"] if x != lesson_id]
                _save(cls)
    return True


def _lesson_file_row(lesson_id: str, f: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": f["id"], "filename": f["filename"], "size": f["size"], "viewable": bool(f.get("viewable")),
            "image": f["ext"] in IMAGE_EXTS, "url": f"/api/v1/classroom/lessons/{lesson_id}/files/{f['id']}"}


def _check_upload(filename: str, data: bytes):
    name = Path(str(filename or "")).name.strip()[:120]
    ext = Path(name).suffix.lower()
    if ext not in UPLOAD_TYPES:
        raise ValueError("课件请用 PDF、图片（PNG / JPG）或 PPT")
    if not data:
        raise ValueError("这个文件是空的")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"文件太大了，最多 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    return name, ext


def add_lesson_file(lesson_id: str, filename: str, data: bytes) -> Dict[str, Any]:
    """课里的配图（某一页用）或附件（整份 PDF / PPT 课件）。"""
    name, ext = _check_upload(filename, data)
    with _LOCK:
        lesson = get_lesson(lesson_id)
        if not lesson or not is_custom_id(lesson_id):
            raise KeyError(lesson_id)
        fid = "lf-" + secrets.token_hex(6)
        d = LESSON_FILES_DIR / lesson_id
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{fid}{ext}").write_bytes(data)
        f = {"id": fid, "filename": name, "ext": ext, "size": len(data), "viewable": UPLOAD_TYPES[ext][1], "uploaded_at": now_iso()}
        lesson.setdefault("files", []).append(f)
        _write_lesson(lesson)
    return _lesson_file_row(lesson_id, f)


def lesson_file(lesson_id: str, fid: str) -> Optional[Dict[str, Any]]:
    f = next((f for f in ((get_lesson(lesson_id) or {}).get("files") or []) if f["id"] == fid), None)
    path = LESSON_FILES_DIR / lesson_id / f"{fid}{f['ext']}" if f else None
    if not path or not path.exists():
        return None
    return {"path": path, "filename": f["filename"], "media_type": UPLOAD_TYPES[f["ext"]][0], "viewable": f["viewable"]}


def remove_lesson_file(lesson_id: str, fid: str) -> bool:
    with _LOCK:
        lesson = get_lesson(lesson_id)
        f = next((f for f in ((lesson or {}).get("files") or []) if f["id"] == fid), None)
        if not f or not is_custom_id(lesson_id):
            return False
        lesson["files"] = [x for x in lesson["files"] if x["id"] != fid]
        for sl in lesson["slides"]:
            if sl.get("image") == fid:
                sl.pop("image")
        _write_lesson(lesson)
        try:
            (LESSON_FILES_DIR / lesson_id / f"{fid}{f['ext']}").unlink()
        except OSError:
            pass
    return True


def lesson_card(lesson: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": lesson["id"], "title": lesson["title"], "grade": lesson.get("grade"), "subject": lesson.get("subject", ""),
            "minutes": lesson.get("minutes", 40), "textbook": lesson.get("textbook") or {}, "summary": lesson.get("summary", ""),
            "builtin": lesson["id"] in LESSONS_BY_ID, "owner_name": lesson.get("owner_name", ""),
            "n_slides": len(lesson["slides"]), "n_tasks": len(lesson["tasks"])}


def lesson_full(lesson: Dict[str, Any]) -> Dict[str, Any]:
    files = {f["id"]: _lesson_file_row(lesson["id"], f) for f in lesson.get("files") or []}
    slides, used = [], set()
    for s in lesson["slides"]:
        row = {k: v for k, v in s.items() if k not in ("figure", "figures", "image")}
        names = s.get("figures") or ([s["figure"]] if s.get("figure") else [])
        row["figure_names"] = [n for n in names if n in FIGURES]
        row["figures"] = [FIGURES[n] for n in row["figure_names"]]
        if s.get("image") in files:
            row["image"], row["image_url"] = s["image"], files[s["image"]]["url"]
            used.add(s["image"])
        slides.append(row)
    tasks = [dict(t, task_id=task_id(lesson["id"], t["key"]), kind_name=KIND_NAMES[t["kind"]]) for t in lesson["tasks"]]
    # 没有被哪一页当配图用的文件，就是附件（整份的 PDF / PPT 课件）
    return dict(lesson_card(lesson), objectives=lesson.get("objectives") or [], slides=slides, tasks=tasks,
                files=[f for fid, f in files.items() if fid not in used])


# ---------------------------------------------------------------------------
#  班级
# ---------------------------------------------------------------------------
def _path(code: str) -> Path:
    return CLASSES_DIR / f"{code}.json"


def norm_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(code or "").upper())


def load(code: str) -> Optional[Dict[str, Any]]:
    code = norm_code(code)
    if not code or not _path(code).exists():
        return None
    try:
        return json.loads(_path(code).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save(cls: Dict[str, Any]) -> None:
    CLASSES_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path(cls["code"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(cls, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_path(cls["code"]))


def create(name: str, teacher_id: str, teacher_name: str, lesson_ids: List[str]) -> Dict[str, Any]:
    name = str(name or "").strip()[:40]
    if not name:
        raise ValueError("请给班级起个名字")
    lessons = _own_lessons(lesson_ids or [l["id"] for l in LESSONS], teacher_id)
    with _LOCK:
        for _ in range(50):
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))
            if not _path(code).exists():
                break
        cls = {"code": code, "name": name, "teacher_id": teacher_id, "teacher_name": teacher_name,
               "created_at": now_iso(), "lesson_ids": lessons, "members": [], "uploads": []}
        _save(cls)
    return cls


def _own_lessons(lesson_ids: List[str], teacher_id: str) -> List[str]:
    """一个班能挂的课：样板课，和这位老师自己的课。"""
    out = []
    for lid in lesson_ids or []:
        lesson = get_lesson(lid)
        if lesson and lid not in out and (lid in LESSONS_BY_ID or lesson.get("owner_id") == teacher_id):
            out.append(lid)
    return out


def set_lessons(code: str, lesson_ids: List[str]) -> Optional[Dict[str, Any]]:
    with _LOCK:
        cls = load(code)
        if not cls:
            return None
        cls["lesson_ids"] = _own_lessons(lesson_ids, cls.get("teacher_id", ""))
        _save(cls)
    return cls


def classes_of(teacher_id: Optional[str]) -> List[Dict[str, Any]]:
    """`None` = 全部（研究员）。"""
    if not CLASSES_DIR.exists():
        return []
    out = []
    for p in sorted(CLASSES_DIR.glob("*.json")):
        cls = load(p.stem)
        if cls and (teacher_id is None or cls.get("teacher_id") == teacher_id):
            out.append(cls)
    return sorted(out, key=lambda c: c.get("created_at") or "", reverse=True)


def join(code: str, who: str, name: str) -> Optional[Dict[str, Any]]:
    """记一笔「谁进了这个班」。同一个人进两次只算一次。"""
    with _LOCK:
        cls = load(code)
        if not cls:
            return None
        if who and not any(m.get("who") == who for m in cls["members"]):
            cls["members"].append({"who": who, "name": str(name or "")[:40], "joined_at": now_iso()})
            _save(cls)
    return cls


def public(cls: Dict[str, Any]) -> Dict[str, Any]:
    """学生看得到的那部分：没有成员名单。"""
    return {"code": cls["code"], "name": cls["name"], "teacher_name": cls.get("teacher_name", ""),
            "lessons": [lesson_card(l) for l in (get_lesson(i) for i in cls.get("lesson_ids", [])) if l],
            "uploads": [upload_row(cls["code"], u) for u in cls.get("uploads", [])]}


def upload_row(code: str, u: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": u["id"], "lesson_id": u.get("lesson_id", ""), "filename": u["filename"], "size": u["size"],
            "viewable": bool(u.get("viewable")), "uploaded_at": u.get("uploaded_at"),
            "url": f"/api/v1/classroom/classes/{code}/courseware/{u['id']}"}


def add_upload(code: str, lesson_id: str, filename: str, data: bytes) -> Dict[str, Any]:
    name, ext = _check_upload(filename, data)
    with _LOCK:
        cls = load(code)
        if not cls:
            raise KeyError(code)
        fid = "cw-" + secrets.token_hex(6)
        d = FILES_DIR / cls["code"]
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{fid}{ext}").write_bytes(data)
        u = {"id": fid, "lesson_id": lesson_id if get_lesson(lesson_id) else "", "filename": name, "ext": ext,
             "size": len(data), "viewable": UPLOAD_TYPES[ext][1], "uploaded_at": now_iso()}
        cls["uploads"].append(u)
        _save(cls)
    return upload_row(cls["code"], u)


def upload_file(code: str, fid: str) -> Optional[Dict[str, Any]]:
    cls = load(code)
    u = next((u for u in (cls or {}).get("uploads", []) if u["id"] == fid), None)
    if not u:
        return None
    path = FILES_DIR / cls["code"] / f"{u['id']}{u['ext']}"
    if not path.exists():
        return None
    return {"path": path, "filename": u["filename"], "media_type": UPLOAD_TYPES[u["ext"]][0], "viewable": u["viewable"]}


def remove_upload(code: str, fid: str) -> bool:
    with _LOCK:
        cls = load(code)
        u = next((u for u in (cls or {}).get("uploads", []) if u["id"] == fid), None)
        if not u:
            return False
        cls["uploads"] = [x for x in cls["uploads"] if x["id"] != fid]
        _save(cls)
        try:
            (FILES_DIR / cls["code"] / f"{u['id']}{u['ext']}").unlink()
        except OSError:
            pass
    return True


def tag_of(meta: Dict[str, Any]) -> Dict[str, Any]:
    """一条 session 的课堂标签，没有就是空的。"""
    return dict(((meta.get("routing") or {}).get("classroom")) or {})


register()
