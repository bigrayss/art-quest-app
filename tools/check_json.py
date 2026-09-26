# -*- coding: utf-8 -*-
"""扫一遍数据目录，看每个文件到底是什么、能不能正常读出来。

写这个是因为「打开 data/ 看到一堆乱码」——**大部分时候那不是乱码**：
`.jsonl.gz` 是压缩过的日志、`.png` 是画，用文本编辑器打开当然是二进制。
但也有真会乱的情况（编辑器按 GBK 打开 UTF-8、某个文件被半路写坏），
所以这里逐个文件给出结论，而不是靠猜。

    python3 tools/check_json.py                # 扫 $ARTQUEST_DATA_DIR
    python3 tools/check_json.py --dir data     # 扫指定目录
    python3 tools/check_json.py --show <file>  # 把某个文件（含 .gz）按 UTF-8 打出来
"""
import argparse
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from artquest import config  # noqa: E402

TEXT = {".json", ".jsonl", ".txt", ".csv", ".md"}
BINARY = {".png", ".jpg", ".jpeg", ".webp", ".woff2", ".gz"}


def _read_text(path: Path) -> str:
    """`.gz` 先解压。两种都按 UTF-8 读——这个项目写出去的一律是 UTF-8。"""
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return fh.read()
    return path.read_text(encoding="utf-8")


def check_file(path: Path) -> dict:
    out = {"path": path, "size": path.stat().st_size, "kind": "", "ok": True, "note": ""}
    suf = path.suffix.lower()
    inner = Path(path.stem).suffix.lower() if suf == ".gz" else suf

    if suf in BINARY and inner not in (".json", ".jsonl"):
        out["kind"] = "二进制"
        out["note"] = "图片/字体，本来就不是文本——编辑器里看是乱码，正常"
        return out
    if inner not in (".json", ".jsonl"):
        out["kind"] = "文本"
        return out

    out["kind"] = "JSONL(gz)" if suf == ".gz" else ("JSON" if inner == ".json" else "JSONL")
    try:
        text = _read_text(path)
    except UnicodeDecodeError as e:
        out["ok"] = False
        out["note"] = f"**不是 UTF-8**：{e}"
        return out
    except OSError as e:
        out["ok"] = False
        out["note"] = f"读不开：{e}"
        return out

    if text.startswith("﻿"):
        out["ok"] = False
        out["note"] = "开头有 BOM —— json.load 会当场报错，八成是被某个编辑器另存过"

    try:
        if inner == ".json":
            json.loads(text)
        else:
            bad = [i + 1 for i, ln in enumerate(text.splitlines())
                   if ln.strip() and _broken(ln)]
            if bad:
                out["ok"] = False
                out["note"] = f"第 {bad[:5]} 行不是合法 JSON"
    except json.JSONDecodeError as e:
        out["ok"] = False
        out["note"] = f"JSON 解析失败：{e}"
        return out

    esc = text.count("\\u")
    if esc:
        # 中文被写成 画 不算坏，但读起来像乱码，而这个项目写出去的都该是原字
        out["note"] = (out["note"] + " / " if out["note"] else "") + f"有 {esc} 处 \\u 转义"
    longest = max((len(x) for x in text.splitlines()), default=0)
    if longest > 20000:
        out["note"] = (out["note"] + " / " if out["note"] else "") + f"最长的一行 {longest} 字符"
    return out


def _broken(line: str) -> bool:
    try:
        json.loads(line)
        return False
    except json.JSONDecodeError:
        return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, default=None, help="要扫的目录（默认 $ARTQUEST_DATA_DIR）")
    ap.add_argument("--show", type=Path, default=None, help="把这个文件按 UTF-8 打出来（.gz 自动解压）")
    a = ap.parse_args()

    if a.show:
        try:
            sys.stdout.write(_read_text(a.show))
        except Exception as e:
            print(f"打不开：{e}", file=sys.stderr)
            return 2
        return 0

    root = a.dir or config.DATA_DIR
    if not root.exists():
        print(f"没有这个目录：{root}", file=sys.stderr)
        return 2
    rows = [check_file(p) for p in sorted(root.rglob("*")) if p.is_file()]
    bad = [r for r in rows if not r["ok"]]
    kinds = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1

    print(f"扫了 {root}：{len(rows)} 个文件")
    for k, n in sorted(kinds.items()):
        print(f"  {k or '其它'}: {n}")
    notes = [r for r in rows if r["note"] and r["kind"] != "二进制"]
    if notes:
        print("\n有话要说的：")
        for r in notes[:40]:
            print(f"  {r['path'].relative_to(root)} — {r['note']}")
    print(f"\n**{'有问题的文件：' + str(len(bad)) if bad else '所有 JSON / JSONL 都能正常读出来，没有坏文件。'}**")
    for r in bad:
        print(f"  {r['path'].relative_to(root)} — {r['note']}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
