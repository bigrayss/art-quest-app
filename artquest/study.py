"""Study Mode — researcher-configured conditions, counterbalanced task order.

The app is one product: children always play the same game. Study Mode does not
strip the game away, it *fixes and records* the things that would otherwise vary
silently — which tasks, in what order, under which UI condition, with or without
a reference image, undo, a time limit, or the end-of-session self-report.

The gamification level is a recorded variable (`ui: full | quiet`), never an
unlogged difference: even free play writes `condition` into the session
metadata, so analysis can control for it — or study it on purpose.

Config lives at `$ARTQUEST_DATA_DIR/study.json`; the participant roster (code →
running index, used for balanced ordering) at `$ARTQUEST_DATA_DIR/participants.json`.
Neither file contains real names.
"""
import hashlib
import random
from typing import Any, Dict, List, Optional

from .config import DATA_DIR
from .logstore import read_json, write_json
from .quests import QUESTS
from .storage import now_iso

STUDY_PATH = DATA_DIR / "study.json"
ROSTER_PATH = DATA_DIR / "participants.json"

# Frozen into every session's metadata, study or not.
DEFAULT_CONDITION: Dict[str, Any] = {
    "ui": "full",              # full | quiet — gamification level
    "reference_allowed": True,
    "undo_allowed": True,
    "questionnaire": False,    # 1–5 self-report before the final screen
    "feedback_source": "ai",   # ai | teacher | none
    "time_limit_sec": None,    # overrides the task's own limit when set
}

DEFAULT_STUDY: Dict[str, Any] = {
    "active": False,
    "study_id": "",
    "tasks": [],               # empty = every enabled task
    "order": "latin",          # latin | random | fixed
    "condition": dict(DEFAULT_CONDITION),
    "groups": {},              # optional between-subject arms: {"A": {...condition overrides}}
}

CONDITION_KEYS = set(DEFAULT_CONDITION)


def load_study() -> Dict[str, Any]:
    cfg = read_json(STUDY_PATH) or {}
    out = dict(DEFAULT_STUDY)
    out.update({k: v for k, v in cfg.items() if k in DEFAULT_STUDY})
    out["condition"] = {**DEFAULT_CONDITION, **(cfg.get("condition") or {})}
    return out


def save_study(cfg: Dict[str, Any]) -> Dict[str, Any]:
    merged = load_study()
    merged.update({k: v for k, v in cfg.items() if k in DEFAULT_STUDY})
    merged["condition"] = {**merged["condition"], **{k: v for k, v in (cfg.get("condition") or {}).items() if k in CONDITION_KEYS}}
    write_json(STUDY_PATH, merged)
    return merged


def resolve_condition(overrides: Optional[Dict[str, Any]] = None, group: str = "") -> Dict[str, Any]:
    """The condition to freeze into a session: defaults < study < group < request."""
    study = load_study()
    cond = dict(study["condition"])
    if group and isinstance(study.get("groups"), dict):
        cond.update({k: v for k, v in (study["groups"].get(group) or {}).items() if k in CONDITION_KEYS})
    if overrides:
        cond.update({k: v for k, v in overrides.items() if k in CONDITION_KEYS})
    return cond


# -- participant roster ----------------------------------------------------
def _roster() -> Dict[str, Any]:
    return read_json(ROSTER_PATH) or {}


def register_participant(participant_id: str, anon_id: str = "") -> Dict[str, Any]:
    """Give a participant code a stable running index (used for counterbalancing).

    Stores only the code, an optional device-local anonymous id, and timestamps.
    """
    pid = (participant_id or "").strip()
    if not pid:
        return {"participant_id": "", "index": 0, "known": False}
    roster = _roster()
    rec = roster.get(pid)
    if rec is None:
        rec = {"index": len(roster), "first_seen": now_iso(), "anon_ids": []}
        roster[pid] = rec
    if anon_id and anon_id not in rec["anon_ids"]:
        rec["anon_ids"].append(anon_id)
    rec["last_seen"] = now_iso()
    write_json(ROSTER_PATH, roster)
    return {"participant_id": pid, "index": rec["index"], "known": True}


# -- ordering --------------------------------------------------------------
def _balanced_latin_row(n: int, row: int) -> List[int]:
    """One row of a balanced Latin square: each task appears in each position
    equally often across participants, and every ordered pair is balanced."""
    order = []
    for j in range(n):
        k = j // 2 if j % 2 == 0 else n - 1 - j // 2
        order.append((row + k) % n)
    return order


def _seed(participant_id: str) -> int:
    return int(hashlib.sha256(participant_id.encode("utf-8")).hexdigest()[:8], 16)


def task_sequence(participant_id: str = "", tasks: Optional[List[str]] = None,
                  order: str = "latin", index: Optional[int] = None) -> List[str]:
    """Deterministic per-participant task order — same code always replays."""
    ids = [t for t in (tasks or []) if t] or [q["id"] for q in QUESTS]
    n = len(ids)
    if n <= 1 or order == "fixed" or not participant_id:
        return ids
    if order == "random":
        rnd = random.Random(_seed(participant_id))
        shuffled = list(ids)
        rnd.shuffle(shuffled)
        return shuffled
    row = index if index is not None else _seed(participant_id) % n
    return [ids[i] for i in _balanced_latin_row(n, row % n)]


def assign(participant_id: str = "", anon_id: str = "", group: str = "") -> Dict[str, Any]:
    """Everything the client needs to run one participant through the study."""
    study = load_study()
    reg = register_participant(participant_id, anon_id) if study["active"] else {"index": None}
    seq = task_sequence(participant_id, study["tasks"], study["order"], reg.get("index"))
    return {
        "active": study["active"],
        "study_id": study["study_id"],
        "participant_id": participant_id,
        "participant_index": reg.get("index"),
        "group": group,
        "order": study["order"],
        "sequence": seq,
        "condition": resolve_condition(group=group),
        "assigned_at": now_iso(),
    }
