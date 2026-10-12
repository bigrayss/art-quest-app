#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 docs/任务空间/（README.md + taskspace.json + frames/）。

    .venv/bin/python tools/taskspace_report.py

不改任务库；只读 missions / missions_v2 / static/refs。退出码 1 = 有 blocked 的候选。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from artquest.taskspace.report import write, OUT  # noqa: E402


def main() -> int:
    ts = write()
    s = ts["summary"]
    print(f"候选 {s['candidates']}：clear {s['status']['clear']} · open {s['status']['open']} · blocked {s['status']['blocked']}")
    for k, v in s["failing_rules"].items():
        print(f"  {k}: {v}")
    print(f"写到 {OUT.relative_to(Path.cwd()) if OUT.is_relative_to(Path.cwd()) else OUT}")
    return 1 if s["status"]["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
