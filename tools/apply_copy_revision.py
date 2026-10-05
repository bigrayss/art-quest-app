# -*- coding: utf-8 -*-
"""把用户审过的文案（docs/彩绘冒险_文案新旧对照.json）回写进源文件。

    .venv/bin/python tools/apply_copy_revision.py [对照表.json] [--dry] [--parts UBFAT]
        默认读 docs/彩绘冒险_文案新旧对照.json；--dry 只报告；--parts 只做某几部分（如 --parts T）
    对照表的「原文」必须是**现在代码里**的文案（第二轮起用户的稿子基线还是最早那版，
    要先和上一轮的新版做差，见 memory artquest-copy-revision）。

对照表的编号和 tools/gen_copy_list.py 生成的清单一一对应：
  U  界面文案：en.js 的键（中文原文）和值（英文）；中文原文同时出现在 index.html / app.js / log.js /
     artquest/*.py 里，按「整段、前后不接汉字、不在注释里」的规则替换。带 {变量} 的键，JS 里是
     `${…}` 模板、Python 里是 f-string 的 {…}，按顺序把变量原样接回去。
  B  徽章说明（app.js ALL_BADGES 的 desc）；名字一个没改。
  F  模板反馈（artquest/feedback/template_feedback.py）
  A  彩点的窗（artquest/assist/template_assist.py）
  T  任务题面（artquest/missions_v2.py 的说明/提示，missions_en.V2_EN 的英文）——研究刺激材料，
     调用方要自己升 TASK_VERSION。

找不到源的（拼接出来的句子、后端报错），脚本列出来，人工改。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRY = "--dry" in sys.argv
PARTS = sys.argv[sys.argv.index("--parts") + 1] if "--parts" in sys.argv else "UBFAT"
JSON_PATH = next((a for a in sys.argv[1:] if a.endswith(".json")), None)
CJK = re.compile(r"[一-鿿]")
# 清单里的展示占位 → 代码里的真实变量名（和 gen_copy_list.VARS 反过来）
DISPLAY_VARS = {"{维度}": "{_ZH.get(low, low)}", "{心情}": "{mood}", "{心愿}": None, "{…}": None}

entries = json.load(open(JSON_PATH or ROOT / "docs" / "彩绘冒险_文案新旧对照.json", encoding="utf-8"))["条目"]
report = {"applied": [], "manual": [], "skipped": 0}


def read(p): return (ROOT / p).read_text(encoding="utf-8")
def write(p, s):
    if not DRY:
        (ROOT / p).write_text(s, encoding="utf-8")


# ---------------------------------------------------------------------------
# U：界面文案
# ---------------------------------------------------------------------------
EN_JS = "static/lang/en.js"
KEY_LINE = re.compile(r'^(\s*)"((?:[^"\\]|\\.)*)":\s*"((?:[^"\\]|\\.)*)"(,?\s*)$')
PH = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_.(), ]*\}")          # 真键里的占位 {n} {a} {wish} {_ZH.get(low, low)}
DPH = re.compile(r"\{(…|心愿|心情|维度|[a-zA-Z_]\w*)\}")       # 清单里的展示占位（{c} 这种没被折叠的也算）


def unesc(s): return s.replace('\\"', '"').replace("\\n", "⏎").replace("\\\\", "\\")
def esc(s): return s.replace("\\", "\\\\").replace('"', '\\"').replace("⏎", "\\n")


def real_key(new_disp, old_key):
    """把清单里的新中文（带 {…} 展示占位）变回带真实变量名的键：变量按在旧键里的顺序接回去。"""
    names = PH.findall(old_key)
    slots = DPH.findall(new_disp)
    if len(names) != len(slots):
        return None
    out, i = [], 0
    pos = 0
    for m in DPH.finditer(new_disp):
        out.append(new_disp[pos:m.start()]); out.append(names[i]); i += 1; pos = m.end()
    out.append(new_disp[pos:])
    return "".join(out)


def key_regex(key, lang):
    """旧键 → 在源码里找它的正则。{x} 在 JS 里对应 ${…}，在 Python 里对应 {…}；其余逐字。"""
    parts = []
    for i, piece in enumerate(PH.split(key)):
        parts.append(re.escape(piece).replace("⏎", r"\\n"))
        if i < len(PH.findall(key)):
            parts.append(r"(\$\{[^}]*\}|\{[^}]*\})" if lang == "js" else r"(\{[^}]*\})")
    return "(?<![一-鿿])" + "".join(parts) + "(?![一-鿿])"


def sub_with_vars(new_key, m):
    """用匹配到的变量表达式（按顺序）填进新键。"""
    vals = list(m.groups())
    out, i = [], 0
    pos = 0
    for ph in PH.finditer(new_key):
        out.append(new_key[pos:ph.start()]); out.append(vals[i] if i < len(vals) else ph.group(0)); i += 1; pos = ph.end()
    out.append(new_key[pos:])
    return "".join(out).replace("⏎", "\\n")


def replace_in_source(path, old_key, new_key, lang):
    """跳过注释行 / HTML 注释块；返回替换次数。"""
    src = read(path)
    rx = re.compile(key_regex(old_key, lang))
    lines = src.split("\n")
    n = 0
    in_html_comment = False
    for idx, line in enumerate(lines):
        st = line.strip()
        if lang == "html":
            if in_html_comment:
                if "-->" in line: in_html_comment = False
                continue
            if st.startswith("<!--"):
                if "-->" not in line: in_html_comment = True
                continue
        elif lang == "js":
            if st.startswith("//") or st.startswith("*") or st.startswith("/*"): continue
        else:
            if st.startswith("#"): continue
        new_line, k = rx.subn(lambda m: sub_with_vars(new_key, m), line)
        if k:
            lines[idx] = new_line; n += k
    if n:
        write(path, "\n".join(lines))
    return n


SOURCES = [("static/index.html", "html"), ("static/app.js", "js"), ("static/log.js", "js"),
           ("artquest/main.py", "py"), ("artquest/accounts.py", "py"), ("artquest/study.py", "py"),
           ("artquest/storage.py", "py"), ("artquest/teacher_pool.py", "py"), ("artquest/gallery.py", "py")]


DISP = {"{_ZH.get(low, low)}": "{维度}", "{mood}": "{心情}", "{wish}": "{心愿}", "{intent}": "{心愿}", "{a}": "{…}", "{b}": "{…}", "{n}": "{…}"}
def disp(s):
    for k, v in DISP.items(): s = s.replace(k, v)
    return s.replace("|", "\\|").replace("\n", "<br>").strip()


def apply_ui():
    lines = read(EN_JS).split("\n")
    by_disp = {}
    for i, l in enumerate(lines):
        m = KEY_LINE.match(l)
        if m: by_disp.setdefault(disp(unesc(m.group(2))), []).append(i)
    for e in [e for e in entries if e["编号"].startswith("U")]:
        if not e["改动字段"]:
            report["skipped"] += 1; continue
        cand = by_disp.get(e["原文"]["中文"].strip(), [])
        if len(cand) != 1:
            report["manual"].append((e["编号"], f"en.js 里按原文找到 {len(cand)} 行", e["原文"]["中文"], e["新版"]["中文"])); continue
        li = cand[0]
        m = KEY_LINE.match(lines[li])
        old_key, old_en = unesc(m.group(2)), unesc(m.group(3))
        new_en = e["新版"]["英文"]
        new_key = old_key
        if "中文" in e["改动字段"]:
            new_key = real_key(e["新版"]["中文"], old_key)
            if new_key is None:
                report["manual"].append((e["编号"], "占位符数量对不上", old_key, e["新版"]["中文"])); continue
            hits = {}
            for path, lang in SOURCES:
                k = replace_in_source(path, old_key, new_key, lang)
                if k: hits[path] = k
            if not hits:
                # en.js 照样换（键是中文原文，拼接出来的句子也要对得上）；源码那头人工改
                report["manual"].append((e["编号"], "源码里找不到（拼接或别处）", old_key, new_key))
            else:
                report["applied"].append((e["编号"], old_key, new_key, hits))
        # en.js 本行：键和值一起换（值里的 {n} 展示成 {…}，按旧值的变量名接回去）
        new_en_real = real_key(new_en, old_en) if DPH.search(new_en) else new_en
        if new_en_real is None:
            report["manual"].append((e["编号"], "英文占位符对不上", old_en, new_en)); new_en_real = old_en
        lines[li] = f'{m.group(1)}"{esc(new_key)}": "{esc(new_en_real)}"{m.group(4)}'
    write(EN_JS, "\n".join(lines))


# ---------------------------------------------------------------------------
# B：徽章说明
# ---------------------------------------------------------------------------
def apply_badges():
    src = read("static/app.js")
    for e in entries:
        if not e["编号"].startswith("B") or "说明" not in e["改动字段"]: continue
        old = f'name: "{e["原文"]["名字"]}", desc: "{e["原文"]["说明"]}"'
        new = f'name: "{e["新版"]["名字"]}", desc: "{e["新版"]["说明"]}"'
        assert e["原文"]["名字"] == e["新版"]["名字"], e["编号"]
        if src.count(old) != 1:
            report["manual"].append((e["编号"], "徽章找不到", old, new)); continue
        src = src.replace(old, new); report["applied"].append((e["编号"], e["原文"]["说明"], e["新版"]["说明"], {"app.js": 1}))
    write("static/app.js", src)


# ---------------------------------------------------------------------------
# F / A：Python 里的句子（f-string 的 {变量} 原样留着）
# ---------------------------------------------------------------------------
def py_literal(disp, vars_map):
    s = disp
    for k, v in vars_map.items(): s = s.replace(k, v)
    return s


def apply_py_strings(prefix, path, vars_map):
    src = read(path)
    for e in entries:
        if not e["编号"].startswith(prefix) or "中文" not in e["改动字段"]: continue
        old, new = py_literal(e["原文"]["中文"], vars_map), py_literal(e["新版"]["中文"], vars_map)
        c = src.count(f'"{old}"')
        if c == 0:
            report["manual"].append((e["编号"], f"{path} 里找不到", old, new)); continue
        src = src.replace(f'"{old}"', f'"{new}"'); report["applied"].append((e["编号"], old, new, {path: c}))
    write(path, src)


# ---------------------------------------------------------------------------
# T：任务题面
# ---------------------------------------------------------------------------
def apply_tasks():
    zh = read("artquest/missions_v2.py"); en = read("artquest/missions_en.py")
    for e in entries:
        if not e["编号"].startswith("T") or not e["改动字段"]: continue
        o, n = e["原文"], e["新版"]
        fam, code = o["id"].split("_")
        # 用原题目 + 原说明定位（题目本身也可能改）
        # 中文：_f("A1", BOTH, "题目", "说明", "提示"...)
        rx = re.compile(r'_f\("' + re.escape(code) + r'",\s*\w+,\s*"' + re.escape(o["题目"]) + r'",\s*"' + re.escape(o["说明"]) + r'"(,\s*"' + re.escape(o["提示"]) + r'")?')
        ms = [m for m in rx.finditer(zh)]
        # 同一个 code 在十个家族里都有（A1…），用说明原文定位，必须唯一
        if len(ms) != 1:
            report["manual"].append((e["编号"], f"missions_v2 定位到 {len(ms)} 处", o["说明"], n["说明"])); continue
        m = ms[0]
        rep = f'_f("{code}", ' + re.search(r',\s*(\w+),', m.group(0)).group(1) + f', "{n["题目"]}", "{n["说明"]}"'
        rep += f', "{n["提示"]}"' if n["提示"] else (f', ""' if m.group(1) else "")
        zh = zh[:m.start()] + rep + zh[m.end():]
        # 英文：V2_EN["M0_A1"] = {"title": …, "instruction": …, "hint": …}
        erx = re.compile(r'("' + re.escape(o["id"]) + r'":\s*\{"title":\s*)"((?:[^"\\]|\\.)*)"(,\s*"instruction":\s*)"((?:[^"\\]|\\.)*)"(,\s*"hint":\s*"(?:[^"\\]|\\.)*")?')
        em = erx.search(en)
        if not em:
            report["manual"].append((e["编号"], "missions_en 里找不到", o["id"], "")); continue
        tail = em.group(5) or ""
        en = en[:em.start()] + f'{em.group(1)}"{n["题目(en)"]}"{em.group(3)}"{n["说明(en)"]}"{tail}' + en[em.end():]
        report["applied"].append((e["编号"], o["说明"], n["说明"], {"missions_v2.py": 1, "missions_en.py": 1}))
    write("artquest/missions_v2.py", zh); write("artquest/missions_en.py", en)


def main():
    if "U" in PARTS: apply_ui()
    if "B" in PARTS: apply_badges()
    if "F" in PARTS: apply_py_strings("F", "artquest/feedback/template_feedback.py", {"{心情}": "{mood}", "{心愿}": "{wish}", "{维度}": "{_ZH.get(low, low)}"})
    if "A" in PARTS: apply_py_strings("A", "artquest/assist/template_assist.py", {"{心愿}": "{intent}"})
    if "T" in PARTS: apply_tasks()
    print(f"{'DRY RUN  ' if DRY else ''}applied {len(report['applied'])}, untouched {report['skipped']}, manual {len(report['manual'])}")
    for x in report["manual"]:
        print("  MANUAL", x)
    return 0


if __name__ == "__main__":
    sys.exit(main())
