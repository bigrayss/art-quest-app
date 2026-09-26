# -*- coding: utf-8 -*-
"""Remove one participant's data, because they asked to withdraw.

Everywhere else in this project the rule is *flag, never delete* — a failed
quality check is a flag, an undone stroke stays in the log. Withdrawal is the
one place that rule is inverted: consent can be taken back, and then the data
has to actually go, not be marked as ignorable.

Deliberately a CLI and not an HTTP endpoint. A research server that can be asked
to delete a child's work over the network is a worse thing to run than one that
cannot; a withdrawal is a human decision with a paper trail behind it, and the
person making it can run a command.

    python3 tools/withdraw.py P007                 # dry run: shows what would go
    python3 tools/withdraw.py P007 --confirm P007  # actually removes it
    python3 tools/withdraw.py P007 --confirm P007 --receipt out.json
    python3 tools/withdraw.py P007 --confirm P007 --account-id acc-…   # 连账号一起删

Dry run 的回执里有 `accounts_seen`：这些作品挂在哪些账号下。账号里有孩子自己起的
名字，所以真要删干净得把它也点名（`--account-id`）——工具不替你猜，一台共用设备上
按 `--anon-id` 找出来的作品可能分属好几个人。
"""
import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from artquest import config  # noqa: E402
from artquest import history as history_mod  # noqa: E402
from artquest.accounts import AccountStore  # noqa: E402
from artquest.logstore import read_json, write_json  # noqa: E402
from artquest.storage import sid_of  # noqa: E402


def find(participant_id: str, anon_id: str = "", account_id: str = "") -> List[Dict[str, Any]]:
    """Every session belonging to this participant, finished or not.

    这里把几个身份**并起来**，而 `history.sessions_for` 里它们是有优先级的——
    两处要的东西不一样。分析里合并身份会捏造出一个不存在的被试；撤回里漏掉一个
    身份，就是答应了删除却留下了一批数据。撤回宁可多删自己的，不可少删。
    """
    found: Dict[str, Dict[str, Any]] = {}
    if participant_id or anon_id:
        for m in history_mod.sessions_for(participant_id, anon_id, finished_only=False):
            found[sid_of(m)] = m
    if account_id:
        acc = AccountStore().load(account_id)
        for m in history_mod.sessions_for("", "", account_id=account_id,
                                          windows=AccountStore().device_windows(acc) if acc else {},
                                          finished_only=False):
            found[sid_of(m)] = m
    return sorted(found.values(), key=lambda m: (m.get("created_at") or "", sid_of(m)))


def receipt_for(participant_id: str, metas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """What was removed, with no content in it.

    A withdrawal still has to be auditable — "we removed 5 sessions on this
    date" — without keeping the thing that was withdrawn.
    """
    return {
        "participant_id": participant_id,
        "withdrawn_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "sessions_removed": len(metas),
        "session_ids": [sid_of(m) for m in metas],
        "task_ids": sorted({m.get("quest_id") for m in metas if m.get("quest_id")}),
        # 这些作品挂在哪些账号下。账号里有孩子自己起的名字，所以要删得干净
        # 就得连它一起删——用 --account-id 指名道姓，不猜。
        "accounts_seen": sorted({(m.get("participant") or {}).get("account_id")
                                 for m in metas if isinstance(m.get("participant"), dict)
                                 and (m.get("participant") or {}).get("account_id")}),
        "note": "content deleted on request; this record keeps no artwork, logs or text",
    }


def withdraw(participant_id: str, anon_id: str = "", account_id: str = "",
             *, confirm: bool = False) -> Dict[str, Any]:
    metas = find(participant_id, anon_id, account_id)
    receipt = receipt_for(participant_id, metas)
    receipt["account_removed"] = False
    if not confirm:
        receipt["dry_run"] = True
        return receipt

    for meta in metas:
        sid = sid_of(meta)
        if sid:
            shutil.rmtree(config.SESSIONS_DIR / sid, ignore_errors=True)

    # the roster maps a code to a running index used for counterbalancing; the
    # code itself goes, but the index stays taken so nobody else inherits their
    # task order and quietly becomes them in the analysis
    roster_path = config.DATA_DIR / "participants.json"
    roster = read_json(roster_path) or {}
    if participant_id in roster:
        roster[participant_id] = {"index": roster[participant_id].get("index"),
                                  "withdrawn": True,
                                  "withdrawn_at": receipt["withdrawn_at"]}
        write_json(roster_path, roster)

    # 账号连着孩子自己起的名字，收回同意之后它不该留下
    if account_id:
        receipt["account_removed"] = AccountStore().delete(account_id)
    receipt["dry_run"] = False
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("participant_id")
    ap.add_argument("--anon-id", default="", help="也按设备 id 查找（没有代号时）")
    ap.add_argument("--account-id", default="", help="连账号一起删（名字和暗号都在里面）")
    ap.add_argument("--confirm", default="", metavar="PARTICIPANT_ID",
                    help="重复一遍代号以真正删除；不给就是 dry run")
    ap.add_argument("--receipt", type=Path, default=None, help="把回执写到这个文件")
    a = ap.parse_args()

    confirmed = a.confirm == a.participant_id
    if a.confirm and not confirmed:
        print(f"--confirm {a.confirm!r} 与 {a.participant_id!r} 不符，未删除任何东西", file=sys.stderr)
        return 2

    receipt = withdraw(a.participant_id, a.anon_id, a.account_id, confirm=confirmed)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    if not confirmed:
        print(f"\n这是 dry run。确实要删除请加：--confirm {a.participant_id}", file=sys.stderr)
    if a.receipt:
        a.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
