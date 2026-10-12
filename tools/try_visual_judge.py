#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在有模型 key 的机器上实测视觉判断器（用户自己跑，见记忆 env-key-off-limits）：

    ARTQUEST_LLM_PROVIDER=openai … .venv/bin/python tools/try_visual_judge.py [stimulus_id ...]

先跑探针（两张左右相反的图，同一问题，答案必须相反），探针不过就不往下跑。
然后对给定材料（默认 m2_scene_a）跑依赖式问题，打印每项状态；请求失败 / 解析失败另列，不记成「无法判断」。
不打印 key，不打印请求头。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from artquest.taskspace.materials import check_material  # noqa: E402
from artquest.taskspace.vision import VisualJudge, probe  # noqa: E402


def main() -> int:
    judge = VisualJudge()
    tmp = Path(__file__).resolve().parents[1] / "data" / "_visual_probe"
    try:
        pr = probe(judge, tmp)
    except Exception as e:
        print("探针请求失败：", type(e).__name__, str(e)[:200])
        print(json.dumps(judge.last_errors, ensure_ascii=False, indent=1))
        return 2
    print("探针：", pr)
    if not pr["ok"]:
        print("探针不过：答案没随图变化，不往下跑。")
        return 1
    for sid in (sys.argv[1:] or ["m2_scene_a"]):
        r = check_material(sid, judge=judge)
        print(f"\n== {sid}: {r['status']}")
        for i in r["items"]:
            print(f"  {i['status']:>4}  {i['id']:<16} {i['note']}")
    if judge.last_errors:
        print("\n请求 / 解析失败（没有记成无法判断）：")
        print(json.dumps(judge.last_errors, ensure_ascii=False, indent=1))
    print(f"\n共 {judge.calls} 次调用")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
