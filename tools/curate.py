# -*- coding: utf-8 -*-
"""Pick today's batch for the wall. Meant to be run once a day by cron.

    python3 tools/curate.py                      # dry run: prints what it would offer
    python3 tools/curate.py --confirm            # actually offers them
    python3 tools/curate.py --confirm --k 4 --cooldown 10 --since 2026-09-14

It offers nothing to anybody by itself: each pick becomes a *pending* proposal
that the child answers the next time they open the app, exactly like a teacher's
pin. Nothing appears on the wall until they say yes, and they can take it back.

Why this doesn't sort by score: see the comment above `gallery.curate` — there
is no total score to sort by, offline four of the nine dimensions are not
judged at all, and a daily published rank is the one verdict this app exists to
avoid handing a child. The batch rotates instead: whoever has not been shown
comes first, one per person per run, then a cool-down.

crontab example (every day at 04:00, project checked out at ~/ArtQuest):

    0 4 * * * cd ~/ArtQuest && .venv/bin/python tools/curate.py --confirm >> logs/curate.log 2>&1
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from artquest import gallery as gallery_mod  # noqa: E402
from artquest.storage import SessionStore  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="挑出今天要挂到图鉴墙上的一批作品（只提议，等本人答应）")
    ap.add_argument("--k", type=int, default=6, help="这一轮最多提议几张")
    ap.add_argument("--since", default="", help="只考虑这个 ISO 时间之后的作品")
    ap.add_argument("--cooldown", type=int, default=7, help="同一个孩子隔几天才会再被挑到")
    ap.add_argument("--confirm", action="store_true", help="真的写进去；不加就是空跑")
    ap.add_argument("--json", action="store_true", help="机器读的输出")
    args = ap.parse_args()

    picks = gallery_mod.curate(k=args.k, since=args.since, cooldown_days=args.cooldown)
    if args.confirm:
        store = SessionStore()
        for p in picks:
            store.propose_featured(p["session_id"], by=gallery_mod.CURATOR_ID, note=p["why"])

    if args.json:
        print(json.dumps({"confirmed": args.confirm, "picks": picks}, ensure_ascii=False))
        return
    if not picks:
        print("今天没有可挂的：要么没有新作品，要么它们的 share_consent 是关的。")
        return
    print(f"{'已提议' if args.confirm else '空跑（加 --confirm 才真的写）'}：{len(picks)} 张")
    for p in picks:
        print(f"  {p['session_id']}  {p['task_id']:<10} {p['person']:<12} 「{p['why']}」")
    if not args.confirm:
        print("\n每一张都还要等本人下次打开 app 时自己答应，才会出现在图鉴里。")


if __name__ == "__main__":
    main()
