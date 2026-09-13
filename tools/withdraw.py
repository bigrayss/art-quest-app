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
from artquest.logstore import read_json, write_json  # noqa: E402


def find(participant_id: str, anon_id: str = "") -> List[Dict[str, Any]]:
    """Every session belonging to this participant, finished or not."""
    return history_mod.sessions_for(participant_id, anon_id, finished_only=False)


def receipt_for(participant_id: str, metas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """What was removed, with no content in it.

    A withdrawal still has to be auditable — "we removed 5 sessions on this
    date" — without keeping the thing that was withdrawn.
    """
    return {
        "participant_id": participant_id,
        "withdrawn_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "sessions_removed": len(metas),
        "session_ids": [m.get("id") for m in metas],
        "task_ids": sorted({m.get("quest_id") for m in metas if m.get("quest_id")}),
        "note": "content deleted on request; this record keeps no artwork, logs or text",
    }


def withdraw(participant_id: str, anon_id: str = "", *, confirm: bool = False) -> Dict[str, Any]:
    metas = find(participant_id, anon_id)
    receipt = receipt_for(participant_id, metas)
    if not confirm:
        receipt["dry_run"] = True
        return receipt

    for meta in metas:
        sid = meta.get("id")
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
    receipt["dry_run"] = False
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("participant_id")
    ap.add_argument("--anon-id", default="", help="也按设备 id 查找（没有代号时）")
    ap.add_argument("--confirm", default="", metavar="PARTICIPANT_ID",
                    help="重复一遍代号以真正删除；不给就是 dry run")
    ap.add_argument("--receipt", type=Path, default=None, help="把回执写到这个文件")
    a = ap.parse_args()

    confirmed = a.confirm == a.participant_id
    if a.confirm and not confirmed:
        print(f"--confirm {a.confirm!r} 与 {a.participant_id!r} 不符，未删除任何东西", file=sys.stderr)
        return 2

    receipt = withdraw(a.participant_id, a.anon_id, confirm=confirmed)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    if not confirmed:
        print(f"\n这是 dry run。确实要删除请加：--confirm {a.participant_id}", file=sys.stderr)
    if a.receipt:
        a.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
