#!/usr/bin/env python3
"""回收没花掉的票。

每台设备联网时都会把自己的备用创作名额补满，而设备可能再也不回来（换了机器、
清了浏览器数据、孩子做完了）。那些票在服务器上是一个个空目录，越攒越多，
`SessionStore.list()` 每次都要把它们走一遍。

**删一张没花掉的票不是「删数据」。** 它里面没有画、没有笔画、没有事件——
只有一个预分配的 id 和一份冻好的条件，从来没有孩子在里面画过一笔。
项目里那条「撤回是唯一一处真删」说的是**作品**；这里删的是一次分配。
为了不出意外，这个脚本只碰同时满足下面三条的目录：

  1. `lifecycle == "issued"`（一旦开始画就会变成 recording，永不回退）
  2. 目录里除了 `session.json` 没有别的文件
  3. 发出来超过 `--days` 天（默认 14）

用法：
    python3 -m tools.reap_tickets --days 14          # 先看会删哪些
    python3 -m tools.reap_tickets --days 14 --apply  # 真的删
"""
import argparse
import datetime as dt
import shutil
import sys

from artquest.config import SESSIONS_DIR
from artquest.logstore import read_json


def stale_tickets(days: int):
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    for d in sorted(SESSIONS_DIR.iterdir()):
        if not d.is_dir():
            continue
        meta = read_json(d / "session.json")
        if not meta or meta.get("lifecycle") != "issued":
            continue
        # 保险起见：目录里只许有 session.json 一个文件
        extra = [p.name for p in d.iterdir() if p.name != "session.json"]
        if extra:
            print(f"  跳过 {d.name}：标着 issued 却有别的文件 {extra}", file=sys.stderr)
            continue
        try:
            issued = dt.datetime.fromisoformat(meta.get("issued_at", ""))
        except ValueError:
            continue
        if issued.tzinfo is None:
            issued = issued.replace(tzinfo=dt.timezone.utc)
        if issued < cutoff:
            yield d, issued


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=14, help="发出多少天以上才回收（默认 14）")
    ap.add_argument("--apply", action="store_true", help="真的删除；不给就只列出来")
    args = ap.parse_args()

    rows = list(stale_tickets(args.days))
    for d, issued in rows:
        print(f"{'删除' if args.apply else '将删除'} {d.name}  发于 {issued:%Y-%m-%d %H:%M}")
        if args.apply:
            shutil.rmtree(d)
    print(f"\n{len(rows)} 张超过 {args.days} 天没花掉的票"
          + ("已回收。" if args.apply else "。加 --apply 才会真的删。"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
