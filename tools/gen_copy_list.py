# -*- coding: utf-8 -*-
"""把 app 里孩子和老师会读到的每一句话拉成一张表，给人审：`docs/文案清单.md` 和 `.docx`。

    python3 tools/gen_copy_list.py            # 需要 pandoc 才出 .docx；没有就只出 .md

来源（都是代码里真用的那份，不是另抄一遍）：
  1. static/lang/en.js      界面上的中文原文（键）和英文（值），按文件里的分节注释分组
  2. static/app.js          徽章的名字和说明（ALL_BADGES）
  3. artquest/feedback/template_feedback.py   模板反馈的固定句
  4. artquest/assist/template_assist.py       彩点的窗里说的话
  5. artquest/missions.py   任务题目、说明、提示（研究刺激材料，改动要记版本）

「标记」一列是机器按几条粗规则挑出来的嫌疑，只是提醒审的人多看一眼，不是结论：
  叹号 / 破折号 / 语气词（吧呀哦啦呢嘛）/ 套话（一起、探索、旅程、奇妙、准备好、哇、太棒、加油、开启、属于你、让我们）/
  长（中文超过 30 字）/ 多问（两个以上问号）。
改文案改源文件，再跑一次这个脚本，表就跟着变。
"""
import re
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from artquest.quests import QUESTS          # noqa: E402
from artquest.missions import TASK_VERSION  # noqa: E402
from artquest import i18n                   # noqa: E402

OUT_MD = ROOT / "docs" / "文案清单.md"
OUT_DOCX = ROOT / "docs" / "文案清单.docx"

CJK = re.compile(r"[\u4e00-\u9fff]")
CLICHE = ["一起", "探索", "旅程", "奇妙", "准备好", "哇", "太棒", "加油", "开启", "属于你", "让我们", "小小", "超级", "魔法"]
PARTICLES = re.compile(r"[吧呀哦啦呢嘛哟][！!。.？?]|[吧呀哦啦呢嘛哟]$")


def flags(zh: str) -> str:
    out = []
    if "！" in zh or "!" in zh:
        out.append("叹号")
    if "——" in zh or "—" in zh:
        out.append("破折号")
    if PARTICLES.search(zh):
        out.append("语气词")
    hit = [w for w in CLICHE if w in zh]
    if hit:
        out.append("套话:" + "/".join(hit))
    if len(CJK.findall(zh)) > 30:
        out.append("长")
    if zh.count("？") + zh.count("?") >= 2:
        out.append("多问")
    return " ".join(out)


def unescape_js(s: str) -> str:
    return s.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8") if "\\u" in s else \
        s.replace('\\"', '"').replace("\\n", "⏎").replace("\\\\", "\\")


def read_en_js():
    """[(section, zh, en)]，按文件顺序。"""
    pat = re.compile(r'^\s*"((?:[^"\\]|\\.)*)":\s*"((?:[^"\\]|\\.)*)",?\s*$')
    section = "补录（后来加的：教师端、门口、版本、隐私）"
    rows = []
    for line in (ROOT / "static" / "lang" / "en.js").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*// -+ (.+?) -+\s*$", line)
        if m:
            section = m.group(1).strip()
            continue
        m = pat.match(line)
        if m:
            rows.append((section, unescape_js(m.group(1)), unescape_js(m.group(2))))
    return rows


def read_badges():
    src = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    start = src.index("const ALL_BADGES = [")
    end = src.index("];", start)
    block = src[start:end]
    rows = []
    for m in re.finditer(r'g:\s*"([^"]*)".*?name:\s*"([^"]*)",\s*desc:\s*"([^"]*)"', block, re.S):
        rows.append((m.group(1), m.group(2), m.group(3)))
    return rows


def read_py_strings(path: Path):
    """文件里所有带中文的字符串字面量，按出现顺序去重。f-string 的 {变量} 原样留着。"""
    src = path.read_text(encoding="utf-8")
    seen = OrderedDict()
    for m in re.finditer(r'(?<![a-zA-Z])f?"((?:[^"\\\n]|\\.)*)"|(?<![a-zA-Z])f?\'((?:[^\'\\\n]|\\.)*)\'', src):
        s = m.group(1) if m.group(1) is not None else m.group(2)
        if s and CJK.search(s) and s not in seen:
            seen[s] = True
    return list(seen)


VARS = {"{_ZH.get(low, low)}": "{维度}", "{mood}": "{心情}", "{wish}": "{心愿}", "{intent}": "{心愿}", "{a}": "{…}", "{b}": "{…}", "{n}": "{…}"}


def cell(s: str) -> str:
    s = s or ""
    for k, v in VARS.items():
        s = s.replace(k, v)
    return s.replace("|", "\\|").replace("\n", "<br>").strip()


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        out.append("| " + " | ".join(cell(x) for x in r) + " |")
    return "\n".join(out)


def build_md() -> str:
    en_rows = read_en_js()
    badges = read_badges()
    fb = read_py_strings(ROOT / "artquest" / "feedback" / "template_feedback.py")
    assist = read_py_strings(ROOT / "artquest" / "assist" / "template_assist.py")

    n_ui = len(en_rows)
    n_task = sum(1 for q in QUESTS if not q.get('legacy'))
    parts = [
        "# 彩绘冒险 · 文案清单",
        "",
        f"界面文案 {n_ui} 条、徽章 {len(badges)} 枚、模板反馈 {len(fb)} 句、彩点的窗 {len(assist)} 句、任务 {n_task} 道（孩子现在看到的 v{TASK_VERSION}）。"
        "由 `tools/gen_copy_list.py` 从代码里抽出来，别手改这个文件；改了源文件再跑一次。",
        "",
        "「标记」是机器按粗规则挑的嫌疑（叹号 / 破折号 / 语气词 / 套话 / 长 / 多问），只是提醒多看一眼。",
        "审的时候直接在「中文」旁边批改就行，英文会跟着中文重译。",
        "",
    ]

    # 1. 界面
    parts.append("## 一、界面文案（static/lang/en.js 的键 = 页面上的中文原文）")
    parts.append("")
    cur = None
    buf = []
    k = 0
    def flush():
        if cur is not None and buf:
            parts.append(f"### {cur}")
            parts.append("")
            parts.append(table(["#", "中文", "英文", "标记"], buf))
            parts.append("")
    for sec, zh, en in en_rows:
        if sec != cur:
            flush(); cur = sec; buf = []
        k += 1
        buf.append((f"U{k}", zh, en, flags(zh)))
    flush()

    # 2. 徽章
    parts.append("## 二、徽章（static/app.js ALL_BADGES）")
    parts.append("")
    parts.append("名字存进了数据（算稀有度），改名字要 bump BADGE_RULES_VERSION；说明随便改。")
    parts.append("")
    parts.append(table(["#", "组", "名字", "说明", "标记"],
                       [(f"B{i+1}", g, n, d, flags(n + d)) for i, (g, n, d) in enumerate(badges)]))
    parts.append("")

    # 3. 反馈
    parts.append("## 三、反馈（artquest/feedback/template_feedback.py）")
    parts.append("")
    parts.append("没接 AI 时孩子看到的就是这些；接了 AI 时，AI 也被要求用「我看到：/ 一个问题：/ 可以试试：」三段开头。`{…}` 是变量。")
    parts.append("")
    parts.append(table(["#", "中文", "标记"], [(f"F{i+1}", s, flags(s)) for i, s in enumerate(fb)]))
    parts.append("")

    # 4. 彩点的窗
    parts.append("## 四、彩点的窗（artquest/assist/template_assist.py）")
    parts.append("")
    parts.append("创作中孩子点开那扇窗，彩点说的一句。")
    parts.append("")
    parts.append(table(["#", "中文", "标记"], [(f"A{i+1}", s, flags(s)) for i, s in enumerate(assist)]))
    parts.append("")

    # 5. 任务
    parts.append("## 五、任务题目（artquest/missions.py）")
    parts.append("")
    parts.append("这是研究刺激材料：改一个字都等于改测量工具，改了要记版本、重跑 `tools/gen_task_list.py`。英文是 missions_en.py 的。")
    parts.append("")
    byfam = OrderedDict()
    TIER = {("simple", "full"): "共通", ("simple",): "小学", ("full",): "初中"}
    for q in QUESTS:
        if q.get("legacy"):
            continue
        byfam.setdefault((q.get("family"), q.get("family_name")), []).append(q)
    t = 0
    for (fam, fname), qs in byfam.items():
        parts.append(f"### {fam} · {fname}")
        parts.append("")
        rows = []
        for q in qs:
            t += 1
            qe = i18n.quest_for(q, "en")
            rows.append((f"T{t}", q.get("id", ""), TIER.get(tuple(q.get("tiers") or []), ""), q.get("title", ""), q.get("instruction", ""), q.get("hint", "") or "",
                         qe.get("title", ""), qe.get("instruction", ""), flags(q.get("instruction", "") + (q.get("hint") or ""))))
        parts.append(table(["#", "id", "版本", "题目", "说明", "提示", "题目(en)", "说明(en)", "标记"], rows))
        parts.append("")
    return "\n".join(parts)


def main() -> int:
    md = build_md()
    OUT_MD.write_text(md, encoding="utf-8")
    print("wrote", OUT_MD.relative_to(ROOT))
    try:
        subprocess.run(["pandoc", str(OUT_MD), "-o", str(OUT_DOCX), "--from", "gfm"], check=True)
        print("wrote", OUT_DOCX.relative_to(ROOT))
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print("docx skipped:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
