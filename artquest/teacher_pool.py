# -*- coding: utf-8 -*-
"""老师打分的池子：每件作品要 K 份老师评分（默认 3），评满就从所有人的待评里消失。

不提前分到人头上（用户 2026-09-30 定的）：谁有空谁评，评过的人不再看到它，
评满 K 次的谁都不再看到。评分数据一条不删，「已评」里各人还能看到自己评过的。
待评排序：已评次数少的在前，让每件尽快凑满；同样少的老作品在前。

K 存在 `data/teacher.json`（研究员接口改），没有就用环境变量 ARTQUEST_RATINGS_PER_WORK，再没有就是 3。
"""
import os
from typing import Any, Dict

from .config import DATA_DIR
from .logstore import read_json, write_json

PATH = DATA_DIR / "teacher.json"
DEFAULT_RATINGS_PER_WORK = 3


def ratings_per_work() -> int:
    data = read_json(PATH) or {}
    try:
        k = int(data.get("ratings_per_work") or os.environ.get("ARTQUEST_RATINGS_PER_WORK") or DEFAULT_RATINGS_PER_WORK)
    except ValueError:
        k = DEFAULT_RATINGS_PER_WORK
    return max(1, k)


def set_ratings_per_work(k: int) -> int:
    data: Dict[str, Any] = read_json(PATH) or {}
    data["ratings_per_work"] = max(1, int(k))
    write_json(PATH, data)
    return data["ratings_per_work"]
