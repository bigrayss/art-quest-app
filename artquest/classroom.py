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


def _plain(label: str, body: str) -> str:
    return _SVG.format(label=label, body=body)


_TXT = '<g fill="currentColor" stroke="none" font-size="13" font-family="sans-serif" text-anchor="middle">'
_DOT = '<g fill="currentColor" stroke="none">'
_LEAF = "q20-30 40 0q-20 30-40 0z"       # 一片叶子，从左尖起笔

FIGURES.update({
    # —— 皮影戏 ——
    "puppet": _plain("皮影人物", '<circle cx="160" cy="34" r="13"/><path d="M146 27l12-17 16 13M173 34h9"/>'
                     '<path d="M149 50h22l9 44h-40z"/><path d="M149 56l-30 18-24-16M171 56l30 16 26-20"/>'
                     '<path d="M150 94l-12 42h-14M170 94l12 42h14"/>'
                     + _DOT + '<circle cx="149" cy="56" r="3.5"/><circle cx="171" cy="56" r="3.5"/><circle cx="119" cy="74" r="3.5"/>'
                     '<circle cx="201" cy="72" r="3.5"/><circle cx="150" cy="94" r="3.5"/><circle cx="170" cy="94" r="3.5"/></g>'
                     '<path d="M95 58L72 142M227 52l24 90M160 62v80" stroke-width="1.5" opacity=".45"/>'),
    "screen": _plain("幕布和灯", '<rect x="70" y="16" width="180" height="96" rx="4"/>'
                     '<g fill="currentColor" stroke="none" opacity=".85"><circle cx="132" cy="46" r="9"/><path d="M124 56h16l6 34h-28z"/>'
                     '<circle cx="190" cy="50" r="8"/><path d="M183 59h14l5 31h-24z"/></g>'
                     '<path d="M140 62l22 6 20-6" stroke-width="2"/>'
                     '<circle cx="290" cy="38" r="9"/><path d="M274 38h-10M278 26l-8-7M278 50l-8 7" stroke-width="2"/>'
                     '<path d="M96 142c0-12 8-18 16-18s16 6 16 18M144 142c0-12 8-18 16-18s16 6 16 18M192 142c0-12 8-18 16-18s16 6 16 18" stroke-width="2" opacity=".5"/>'),
    "joints": _plain("分开的部件", '<circle cx="46" cy="42" r="15"/><path d="M90 24h30l8 50H82z"/>'
                     '<rect x="150" y="26" width="46" height="13" rx="6.5"/><rect x="150" y="54" width="46" height="13" rx="6.5"/>'
                     '<rect x="222" y="20" width="14" height="50" rx="7"/><rect x="254" y="20" width="14" height="50" rx="7"/>'
                     '<path d="M222 96h14v24h14M254 96h14v24h14"/>'
                     + _DOT + '<circle cx="46" cy="57" r="3"/><circle cx="90" cy="30" r="3"/><circle cx="120" cy="30" r="3"/><circle cx="157" cy="32.5" r="3"/>'
                     '<circle cx="189" cy="32.5" r="3"/><circle cx="157" cy="60.5" r="3"/><circle cx="229" cy="27" r="3"/><circle cx="229" cy="63" r="3"/>'
                     '<circle cx="261" cy="27" r="3"/><circle cx="261" cy="63" r="3"/></g>'
                     + _TXT + '<text x="46" y="84">头</text><text x="105" y="94">身</text><text x="173" y="88">手臂</text><text x="245" y="88">腿</text><text x="252" y="140">脚</text></g>'),
    "carve": _plain("镂空的花纹", '<rect x="40" y="16" width="100" height="100" rx="6"/>'
                    '<circle cx="90" cy="66" r="9"/><path d="M90 57V34M90 75v23M81 66H58M99 66h23M84 60L68 44M96 60l16-16M84 72L68 88M96 72l16 16" stroke-width="2.5"/>'
                    '<rect x="180" y="16" width="100" height="100" rx="6" fill="currentColor"/>'
                    '<g stroke="#fff"><circle cx="230" cy="66" r="9"/><path d="M230 57V34M230 75v23M221 66h-23M239 66h23M224 60l-16-16M236 60l16-16M224 72l-16 16M236 72l16 16" stroke-width="2.5"/></g>'
                    + _TXT + '<text x="90" y="138">留线，刻掉底</text><text x="230" y="138">留底，刻掉线</text></g>'),
    # —— 田园村舍 ——
    "house": _plain("白墙黑瓦的房子", '<path d="M16 124h288"/><path d="M70 124V66h170v58"/>'
                    '<path d="M56 66h198l-18-24H74z" fill="currentColor" fill-opacity=".8"/>'
                    '<path d="M56 66V52h-8M254 66V52h8" />'
                    '<path d="M142 124V90h26v34"/><rect x="92" y="82" width="26" height="20"/><rect x="194" y="82" width="26" height="20"/>'
                    '<path d="M105 82v20M207 82v20M92 92h26M194 92h26" stroke-width="1.5"/>'
                    '<path d="M280 124V96"/><circle cx="280" cy="80" r="17"/>'),
    "overlap": _plain("前后遮挡", '<path d="M16 130h288" stroke-width="2" opacity=".5"/>'
                      '<path d="M30 130V84l44-28 44 28v46z"/><path d="M60 130v-24h22v24"/>'
                      '<path d="M118 100V70l36-22 36 22v44h-72"/><rect x="144" y="78" width="18" height="16"/>'
                      '<path d="M190 84V56l30-18 30 18v44h-60"/><rect x="212" y="62" width="14" height="13"/>'
                      '<path d="M250 100h44" stroke-width="2" opacity=".5"/>'
                      + _TXT + '<text x="74" y="146">前：大、低</text><text x="154" y="146">中</text><text x="236" y="146">后：小、高</text></g>'),
    "layers": _plain("近景、中景、远景", '<path d="M8 58q52-46 104 0q48-40 96 0q52-36 104 0" stroke-width="2" opacity=".5"/>'
                     '<path d="M8 84h304"/>'
                     '<path d="M96 84V70l14-9 14 9v14M132 84V66l16-10 16 10v18M172 84V72l12-8 12 8v12" stroke-width="2.5"/>'
                     '<path d="M8 142L128 84M64 142l84-58M124 142l44-58M188 142l-4-58M252 142l-48-58M312 142L228 84" stroke-width="2"/>'
                     + _TXT + '<text x="286" y="30">远：山</text><text x="264" y="78">中：村子</text><text x="40" y="106">近：田</text></g>'),
    "fields": _plain("田地的线条", '<rect x="16" y="20" width="84" height="76" rx="4"/><rect x="118" y="20" width="84" height="76" rx="4"/><rect x="220" y="20" width="84" height="76" rx="4"/>'
                     '<g stroke-width="2"><path d="M30 34v8M44 34v8M58 34v8M72 34v8M86 34v8M37 52v8M51 52v8M65 52v8M79 52v8M30 70v8M44 70v8M58 70v8M72 70v8M86 70v8"/>'
                     '<path d="M118 36h84M118 52h84M118 68h84M118 84h84"/>'
                     '<path d="M220 40q42-18 84 0M220 56q42-18 84 0M220 72q42-18 84 0M220 88q42-18 84 0"/></g>'
                     + _TXT + '<text x="58" y="118">秧苗：短竖线</text><text x="160" y="118">菜地：横线</text><text x="262" y="118">梯田：弧线</text></g>'),
    # —— 藏书票 ——
    "bookplate": _plain("一张藏书票", '<rect x="104" y="6" width="112" height="138" rx="3"/><rect x="112" y="14" width="96" height="122" rx="2" stroke-width="1.5"/>'
                        '<path d="M130 92c10-6 20-6 30 0c10-6 20-6 30 0V62c-10-6-20-6-30 0c-10-6-20-6-30 0zM160 62v30"/>'
                        '<path d="M146 50' + _LEAF + '" fill="currentColor" fill-opacity=".8" stroke-width="2"/>'
                        '<g fill="currentColor" stroke="none" font-family="sans-serif" text-anchor="middle"><text x="160" y="32" font-size="11" letter-spacing="2">EX LIBRIS</text>'
                        '<text x="160" y="124" font-size="13">小禾藏书</text></g>'
                        '<g stroke-width="1.5"><path d="M218 24h30M218 116h30M102 70H72"/></g>'
                        + _TXT + '<text x="272" y="28">标记</text><text x="272" y="120">票主</text><text x="52" y="74">图画</text></g>'),
    "layout": _plain("三种排法", '<rect x="24" y="14" width="76" height="104" rx="3"/><rect x="122" y="14" width="76" height="104" rx="3"/><rect x="220" y="14" width="76" height="104" rx="3"/>'
                     '<rect x="34" y="24" width="56" height="58" fill="currentColor" fill-opacity=".25" stroke-width="2"/><path d="M40 94h44M46 106h32" stroke-width="4"/>'
                     '<path d="M138 28h44M146 106h28" stroke-width="4"/><circle cx="160" cy="66" r="24" fill="currentColor" fill-opacity=".25" stroke-width="2"/>'
                     '<path d="M234 28v76M246 40v52" stroke-width="4"/><rect x="258" y="24" width="28" height="84" fill="currentColor" fill-opacity=".25" stroke-width="2"/>'
                     + _TXT + '<text x="62" y="138">上图下字</text><text x="160" y="138">图在中间</text><text x="258" y="138">左字右图</text></g>'),
    "bw": _plain("黑、白、灰", '<rect x="24" y="16" width="80" height="80" rx="4"/><path d="M44 56' + _LEAF + '" fill="currentColor"/>'
                 '<rect x="120" y="16" width="80" height="80" rx="4" fill="currentColor"/><path d="M140 56' + _LEAF + '" fill="#fff" stroke="#fff"/>'
                 '<rect x="216" y="16" width="80" height="80" rx="4"/>'
                 '<path d="M216 34h80M216 46h80M216 58h80M216 70h80M216 82h80" stroke-width="1.5"/><path d="M236 56' + _LEAF + '" fill="#fff"/>'
                 + _TXT + '<text x="64" y="118">白底黑图</text><text x="160" y="118">黑底白图</text><text x="256" y="118">排线成灰</text></g>'),
})

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
    {
        "id": "zj5a_shadow",
        "title": "皮影戏",
        "grade": 5,
        "subject": "美术 · 设计应用",
        "minutes": 40,
        "textbook": {"edition": "浙人美版 五年级上册（2026 年秋）", "lesson": "第 2 课", "verified": False},
        "summary": "认识皮影戏，设计一个侧脸、能活动、带花纹的皮影人物。",
        "objectives": [
            "知道皮影戏是怎么演的：灯、幕布、皮影。",
            "看得出皮影人物的特点：侧脸、分成几段、有镂空的花纹。",
            "会设计一个自己的皮影人物。",
        ],
        "slides": [
            {"title": "皮影戏", "kind": "cover", "figure": "puppet",
             "lines": ["一盏灯，一块幕布，几个会动的影子。", "今天我们认识皮影，再设计一个皮影人物。"]},
            {"title": "皮影戏是怎么演的", "figure": "screen",
             "lines": ["幕布后面点一盏灯，艺人把皮影贴着幕布操纵，观众在另一边看影子。",
                       "艺人一边动手，一边说唱，旁边还有锣鼓和弦乐伴奏。",
                       "中国皮影戏在 2011 年列入联合国教科文组织的人类非物质文化遗产代表作名录。",
                       "浙江的海宁皮影戏很有名，已经传了好几百年。"],
             "ask": "你看过皮影戏吗？在哪里看的？影子是什么颜色的？"},
            {"title": "皮影人物长什么样", "figure": "puppet",
             "lines": ["脸是侧面的：只看得见一只眼睛，额头、鼻子、下巴连成一条好看的线。",
                       "身体分成好几段，段和段之间用线钉在一起，所以能动。",
                       "三根细杆：一根撑着身体，两根带着两只手。"],
             "ask": "图上的圆点是什么？数一数这个人物有几个地方能动。"},
            {"title": "把人物拆开看", "figure": "joints",
             "lines": ["头、身、上臂、下臂、手、腿、脚，一段一段分开做。",
                       "每一段都要在接头的地方多留出一点，好让两段叠在一起钉住。",
                       "设计的时候先想好：我的人物哪些地方要能动？"]},
            {"title": "镂空的花纹", "figure": "carve",
             "lines": ["皮影是用牛皮、驴皮刻出来再上色的，刻掉的地方透光。",
                       "留线刻底：花纹是线，周围是空的，影子里花纹是深色的。",
                       "留底刻线：花纹是空的，影子里花纹是亮的。",
                       "衣服、帽子上常用的花纹：圆点、水波、花朵、回纹。"],
             "ask": "两张图里，哪一张的花在影子里是亮的？"},
            {"title": "设计一个皮影人物", "figure": "puppet",
             "lines": ["第一步，定角色：是将军、公主、孙悟空，还是你自己？",
                       "第二步，画侧脸和帽子，这是最能看出角色的地方。",
                       "第三步，画身体、手臂和腿，在接头处画上圆点。",
                       "第四步，给衣服添花纹。"]},
            {"title": "动手画", "kind": "tasks",
             "lines": ["课堂练习：先画一张皮影的侧脸，再设计一个完整的皮影人物。", "课后作业：画一出皮影戏里的一幕。"]},
        ],
        "tasks": [
            {"key": "p1", "kind": "practice", "minutes": 10, "title": "皮影的侧脸",
             "instruction": "画一个皮影人物的头：侧面的脸，加上帽子或头饰。",
             "requirements": "脸是侧面的；帽子或头饰上有花纹。",
             "hint": "额头、鼻子、下巴用一条线连着画下来。"},
            {"key": "p2", "kind": "practice", "minutes": 20, "title": "我的皮影人物",
             "instruction": "设计一个完整的皮影人物：侧脸、身体、手臂和腿。在能活动的接头处画上圆点，再给衣服添上花纹。",
             "requirements": "看得出是什么角色；至少有四处接头；衣服上有花纹。",
             "hint": "先想好角色，再从头画起。"},
            {"key": "h1", "kind": "homework", "minutes": 30, "title": "一出戏里的一幕",
             "instruction": "画皮影戏里的一幕：幕布上有两个角色，他们正在做什么？可以是你知道的故事，也可以自己编。",
             "requirements": "有两个角色；看得出他们在做什么；有一点布景，比如树、桌子、城门。",
             "hint": "两个角色脸对着脸，故事就开始了。"},
            {"key": "h2", "kind": "homework", "optional": True, "minutes": 30, "title": "皮影动物",
             "instruction": "设计一个皮影动物：龙、马、老虎、鱼都可以。想一想它哪些地方要能动。",
             "requirements": "动物是侧面的；接头处有圆点；身上有花纹。",
             "hint": "尾巴、脖子、腿，都是可以动的地方。"},
        ],
    },
    {
        "id": "zj5a_village",
        "title": "田园村舍",
        "grade": 5,
        "subject": "美术 · 造型表现",
        "minutes": 40,
        "textbook": {"edition": "浙人美版 五年级上册（2026 年秋）", "lesson": "第 6 课", "verified": False},
        "summary": "看乡村的房子和田地，用前后遮挡和三层景画一幅有远近的田园风景。",
        "objectives": [
            "说得出江南乡村房子的样子：白墙、黑瓦、高出屋顶的山墙。",
            "会用前后遮挡画出一组房子。",
            "会把画面分成近景、中景、远景。",
        ],
        "slides": [
            {"title": "田园村舍", "kind": "cover", "figure": "layers",
             "lines": ["田连着田，房子挨着房子，远处是山。", "今天我们画一幅田园风景。"]},
            {"title": "乡村的房子", "figure": "house",
             "lines": ["浙江乡村的老房子：墙刷成白色，屋顶盖着黑瓦。",
                       "两头的墙比屋顶高出一截，叫马头墙，着火的时候能挡住火。",
                       "门开在中间，窗子不大，房前屋后常有树和菜地。"],
             "ask": "你见过的乡村房子是什么样的？和图上的有什么不一样？"},
            {"title": "房子挨着房子", "figure": "overlap",
             "lines": ["村子里的房子不是排成一排的，是一座挡着一座。",
                       "前面的房子画完整，后面的房子被挡住一部分。",
                       "前面的大一些、位置低一些；后面的小一些、位置高一些。"],
             "ask": "图上三座房子，哪一座离我们最近？你是怎么看出来的？"},
            {"title": "近景、中景、远景", "figure": "layers",
             "lines": ["近景：离我们最近的田地，画得大、画得清楚。",
                       "中景：村子，这是画面里最主要的地方。",
                       "远景：山和天，几条线就够了。",
                       "田垄的线越远越靠拢，画面就有了远近。"]},
            {"title": "田地的线条", "figure": "fields",
             "lines": ["不同的田，用不同的线：秧苗是一排排短竖线，菜地是横线，梯田是一道道弧线。",
                       "近处的线画得疏而粗，远处的线画得密而细。"],
             "ask": "如果要画一片油菜花田，你会用什么样的线或点？"},
            {"title": "怎么画一幅田园风景", "figure": "overlap",
             "lines": ["第一步，画一条地平线，把画面分成天和地。",
                       "第二步，在中间画村子：先画最前面的房子，再画后面的。",
                       "第三步，近处画田地，远处画山。",
                       "第四步，添上树、小路、电线杆、田里的人。"]},
            {"title": "动手画", "kind": "tasks",
             "lines": ["课堂练习：先画一组前后遮挡的房子，再画一幅有三层景的田园风景。", "课后作业：画你见过的一个村子。"]},
        ],
        "tasks": [
            {"key": "p1", "kind": "practice", "minutes": 10, "title": "一组房子",
             "instruction": "画三座挨在一起的乡村房子，让它们一座挡着一座。",
             "requirements": "看得出哪座在前、哪座在后；前面的比后面的大。",
             "hint": "先画最前面的那一座。"},
            {"key": "p2", "kind": "practice", "minutes": 20, "title": "田园风景",
             "instruction": "画一幅田园风景：近处是田地，中间是村子，远处是山。",
             "requirements": "近景、中景、远景都有；田地用上两种不同的线。",
             "hint": "先画地平线，再画村子。"},
            {"key": "h1", "kind": "homework", "minutes": 30, "title": "我见过的村子",
             "instruction": "画一个你去过或见过的村子：老家的、旅行时路过的都可以。把最让你记得的东西画进去——一棵大树、一座桥、一口池塘、晒着的稻谷。",
             "requirements": "房子有前有后；看得出村子周围是什么；有一样你记得最清楚的东西。",
             "hint": "闭上眼睛想一想：你是从哪里看到这个村子的？"},
            {"key": "h2", "kind": "homework", "optional": True, "minutes": 30, "title": "四季的田野",
             "instruction": "选一个季节，画那时候的田野：春天插秧、夏天一片绿、秋天收稻子、冬天下雪。",
             "requirements": "看得出是哪个季节；田里有人或者动物。",
             "hint": "颜色最能说出季节。"},
        ],
    },
    {
        "id": "zj5a_bookplate",
        "title": "藏书票",
        "grade": 5,
        "subject": "美术 · 设计应用",
        "minutes": 40,
        "textbook": {"edition": "浙人美版 五年级上册（2026 年秋）", "lesson": "第 10 课", "verified": False},
        "summary": "认识藏书票，给自己的书设计一张：有图画、有标记、有名字。",
        "objectives": [
            "知道藏书票是什么、贴在哪里、有什么用。",
            "说得出藏书票上的三样东西：图画、标记、票主。",
            "会用黑、白、灰设计一张自己的藏书票。",
        ],
        "slides": [
            {"title": "藏书票", "kind": "cover", "figure": "bookplate",
             "lines": ["贴在书里的一张小画，告诉大家：这本书是我的。", "今天我们给自己的书设计一张藏书票。"]},
            {"title": "藏书票是什么", "figure": "bookplate",
             "lines": ["藏书票是贴在书的扉页上的小版画，说明这本书是谁的。",
                       "它在五百多年前出现在欧洲，后来传到中国。",
                       "因为小巧又精致，人们叫它“纸上宝石”。"],
             "ask": "你会在自己的书上写名字吗？写在哪里？"},
            {"title": "藏书票上有什么", "figure": "bookplate",
             "lines": ["图画：票主喜欢的东西，占的地方最大。",
                       "标记：EX LIBRIS，是拉丁文，意思是“我的藏书”。也可以写中文的“藏书”。",
                       "票主：这本书的主人的名字。"],
             "ask": "看图找一找：图画、标记、票主各在哪里？"},
            {"title": "画什么好", "figure": "layout",
             "lines": ["画你喜欢的：小动物、植物、爱看的故事、爱玩的东西。",
                       "也可以画和书有关的：打开的书、台灯、猫头鹰、书架。",
                       "图和字怎么摆：上图下字、图在中间、左字右图，都可以。"],
             "ask": "如果用一样东西代表你，你会选什么？"},
            {"title": "黑、白、灰", "figure": "bw",
             "lines": ["藏书票大多是版画，颜色少，黑白分明。",
                       "白底黑图：干净、清楚。黑底白图：醒目、有分量。",
                       "排线能排出灰色：线越密越暗。",
                       "一张票里黑、白、灰都有，就耐看。"]},
            {"title": "怎么设计一张藏书票", "figure": "layout",
             "lines": ["第一步，画一个外框，定下票的形状：长方形、圆形、书的形状都行。",
                       "第二步，画主要的图画，画大一些。",
                       "第三步，摆好标记和名字，字要写工整。",
                       "第四步，涂黑、留白、排线，再给外框加一圈花边。"]},
            {"title": "动手画", "kind": "tasks",
             "lines": ["课堂练习：先画一个代表自己的图案，再设计一张完整的藏书票。", "课后作业：给家人或朋友设计一张。"]},
        ],
        "tasks": [
            {"key": "p1", "kind": "practice", "minutes": 10, "title": "代表我的图案",
             "instruction": "选一样能代表你的东西，把它画成一个简单的图案。只用黑色。",
             "requirements": "一眼看得出画的是什么；有涂黑的地方，也有留白的地方。",
             "hint": "形状越简单越好认。"},
            {"key": "p2", "kind": "practice", "minutes": 20, "title": "我的藏书票",
             "instruction": "设计一张自己的藏书票：画上外框和图画，写上“EX LIBRIS”或“藏书”，再写上你的名字。",
             "requirements": "图画、标记、名字三样都有；黑、白、灰都用到。",
             "hint": "先定外框，再画图，最后摆字。"},
            {"key": "h1", "kind": "homework", "minutes": 30, "title": "送给你的藏书票",
             "instruction": "给一位家人或朋友设计一张藏书票。想一想他喜欢什么，把它画进去。",
             "requirements": "看得出是为谁设计的；图画、标记、名字都有；外框有花边。",
             "hint": "先问问他最喜欢的一本书。"},
            {"key": "h2", "kind": "homework", "optional": True, "minutes": 30, "title": "一套藏书票",
             "instruction": "设计一套三张的藏书票，三张用同样的外框，画不同的图，比如同一只猫的三个样子。",
             "requirements": "三张看得出是一套；每张的图不一样。",
             "hint": "外框和字的位置不变，只换图画。"},
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


COURSEWARE_DIR = Path(__file__).resolve().parent.parent / "static" / "classroom"   # 参考课例配的 PDF 课件（tools/build_courseware.py 出）


def builtin_files(lesson: Dict[str, Any]) -> List[Dict[str, Any]]:
    """参考课例自带的整份课件：仓库里的 PDF，走静态文件。"""
    p = COURSEWARE_DIR / f"{lesson['id']}.pdf"
    if lesson["id"] not in LESSONS_BY_ID or not p.exists():
        return []
    return [{"id": "pdf", "filename": f"{lesson['title']} 课件.pdf", "size": p.stat().st_size, "viewable": True,
             "image": False, "url": f"/static/classroom/{lesson['id']}.pdf"}]


def lesson_card(lesson: Dict[str, Any]) -> Dict[str, Any]:
    files = {f["id"]: f for f in lesson.get("files") or []}
    # 封面：第一张示意图，或者第一张配图；都没有就看附件是什么（前端画一个文件的样子）
    cover, cover_url, used = "", "", set()
    for s in lesson["slides"]:
        names = s.get("figures") or ([s["figure"]] if s.get("figure") else [])
        if not cover and not cover_url and names and names[0] in FIGURES:
            cover = FIGURES[names[0]]
        if s.get("image") in files:
            used.add(s["image"])
            if not cover and not cover_url:
                cover_url = _lesson_file_row(lesson["id"], files[s["image"]])["url"]
    attached = [f for fid, f in files.items() if fid not in used]
    builtin = lesson["id"] in LESSONS_BY_ID
    return {"id": lesson["id"], "title": lesson["title"], "grade": lesson.get("grade"), "subject": lesson.get("subject", ""),
            "minutes": lesson.get("minutes", 40), "textbook": lesson.get("textbook") or {}, "summary": lesson.get("summary", ""),
            "builtin": builtin, "owner_name": lesson.get("owner_name", ""),
            "n_slides": len(lesson["slides"]), "n_tasks": len(lesson["tasks"]),
            "cover": cover, "cover_url": cover_url,
            "n_files": len(attached) + len(builtin_files(lesson)),
            "file_ext": (attached[0]["ext"].lstrip(".") if attached else ("pdf" if builtin_files(lesson) else ""))}


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
                files=builtin_files(lesson) + [f for fid, f in files.items() if fid not in used])


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
    lessons = _own_lessons(lesson_ids or [LESSONS[0]["id"]], teacher_id)
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
