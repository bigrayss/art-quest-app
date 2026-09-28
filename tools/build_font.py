#!/usr/bin/env python3
"""把一款中文字体裁成这个 app 真正用得到的那些字。

整包 15MB 不可能塞进一个要离线用的 app。这个脚本按**实际字符集**子集化：

  1. 仓库里所有面向孩子的中文（界面文案、任务标题和提示、徽章名……）
  2. GB2312 一级字库 3755 字——日常中文的覆盖率约 99.7%，
     孩子自己打的字（心愿、代号、给伙伴起的名）也就基本都在里面了
  3. ASCII、常用标点和符号

用法（需要 `pip install fonttools brotli`，只在构建时要，运行时不要）：

    # 正文：全字符集（孩子打的字也要覆盖）
    python3 -m tools.build_font RHR-CN-Medium.ttf static/fonts/rhr-sc-400.woff2
    # 标题：只要仓库里的字（标题从不是孩子输入的）
    python3 -m tools.build_font RHR-CN-Bold.ttf static/fonts/rhr-sc-700.woff2 --repo-only

**改了任何面向孩子的文案都要重跑一次**（尤其加粗那份只含仓库里出现过的字）：漏掉的字会掉到系统字体，
看上去就是「有几个字字体不对」。源字体放在 tools/fonts-src/（不进仓库）：
    python3 -m tools.build_font tools/fonts-src/ResourceHanRoundedCN-Medium.ttf static/fonts/rhr-sc-400.woff2
    python3 -m tools.build_font tools/fonts-src/ResourceHanRoundedCN-Bold.ttf static/fonts/rhr-sc-700.woff2 --repo-only
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 面向孩子的文案散在这些地方
SOURCES = ["static/index.html", "static/app.js", "static/style.css",
           "artquest/missions.py", "artquest/quests.py", "artquest/schemas.py",
           "artquest/feedback", "artquest/scoring", "artquest/rubric.py", "artquest/assist"]


def gb2312_level1() -> set:
    """一级字库：区 16–55，每区 94 位，按拼音序排的 3755 个常用字。"""
    out = set()
    for area in range(16, 56):
        for pos in range(1, 95):
            try:
                out.add(bytes([0xA0 + area, 0xA0 + pos]).decode("gb2312"))
            except UnicodeDecodeError:
                pass
    return out


def repo_chars() -> set:
    out = set()
    for rel in SOURCES:
        p = ROOT / rel
        files = sorted(p.rglob("*.py")) if p.is_dir() else ([p] if p.exists() else [])
        for f in files:
            out |= set(f.read_text(encoding="utf-8", errors="ignore"))
    return {c for c in out if ord(c) > 0x2000}      # 只要非 ASCII 的部分


def charset(repo_only: bool = False) -> set:
    """`repo_only` 给**标题字重**用。

    标题、按钮、任务名这些文案全是仓库里写死的，孩子打的字永远不会加粗
    （正文是 600，走常规字重那一份，那一份带着 GB2312 一级的全量覆盖）。
    所以标题这一份只装仓库里出现过的字就够了，体积能省三分之二。
    """
    base = set(chr(c) for c in range(0x20, 0x7F))                    # ASCII
    base |= set("·—…、。《》「」『』〈〉？！：；，．（）【】“”‘’×÷±°％‰→←↑↓★☆♪√")
    base |= repo_chars()
    if not repo_only:
        base |= gb2312_level1()
    return {c for c in base if c.strip() or c == " "}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    repo_only = "--repo-only" in sys.argv
    if len(args) != 2:
        print(__doc__)
        return 2
    src, dst = Path(args[0]), Path(args[1])
    from fontTools import subset

    chars = charset(repo_only)
    print(f"字符集：{len(chars)} 个（" + ("只要仓库里的字" if repo_only
          else "GB2312 一级 3755 + 仓库里的字") + " + ASCII/标点）")
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.desubroutinize = True
    opts.drop_tables += ["DSIG"]
    opts.layout_features = ["kern", "liga", "locl", "ccmp", "vert", "vrt2"]
    opts.name_IDs = ["*"]           # 名字和许可证信息留着——OFL 要求保留
    opts.name_legacy = True
    opts.notdef_outline = True
    font = subset.load_font(str(src), opts)
    subsetter = subset.Subsetter(options=opts)
    subsetter.populate(text="".join(sorted(chars)))
    subsetter.subset(font)
    dst.parent.mkdir(parents=True, exist_ok=True)
    subset.save_font(font, str(dst), opts)
    print(f"{src.name} {src.stat().st_size/1e6:.1f}MB → {dst} {dst.stat().st_size/1024:.0f}KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
