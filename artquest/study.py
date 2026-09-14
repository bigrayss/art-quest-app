"""Study Mode — researcher-configured conditions, counterbalanced task order.

The app is one product: children always play the same game. Study Mode does not
strip the game away, it *fixes and records* the things that would otherwise vary
silently — which tasks, in what order, under which UI condition, with or without
a reference image, undo, canvas zoom, a time limit, or the end-of-session
self-report.

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
from .quests import QUESTS, QUESTS_BY_ID
from .storage import now_iso

STUDY_PATH = DATA_DIR / "study.json"
ROSTER_PATH = DATA_DIR / "participants.json"

# Frozen into every session's metadata, study or not.
DEFAULT_CONDITION: Dict[str, Any] = {
    "ui": "full",              # full | quiet — gamification level
    "reference_allowed": True,
    "undo_allowed": True,
    "zoom_allowed": True,      # zooming/panning the canvas at all
    "questionnaire": False,    # 1–5 self-report before the final screen
    "feedback_source": "ai",   # ai | teacher | none
    "history_mode": "none",    # none | history | personalized — the personalisation arm
    "growth_display": "full",  # none | badges | full — what the child sees of their own growth
    # Seeing other people's work is an influence on what a child draws, so it is
    # off by default and only ever reachable *after* they submit their own.
    "gallery_display": "none",     # none | after_submit | always
    # Publishing a minor's artwork to other users. Never defaulted to true, never
    # inferred: it mirrors the consent form, frozen per session.
    "share_consent": False,
    "time_limit_sec": None,    # overrides the task's own limit when set
}

# A protocol says which *families* a child must cover, which parallel form they
# get, and what is held out — so that one library of 75 forms turns into a short,
# balanced, reproducible run for each participant.
DEFAULT_PROTOCOL: Dict[str, Any] = {
    "protocol_id": "",
    "required_families": [],   # e.g. ["M1", "M3", "M4", "M6"]; empty = infer from `tasks`
    "task_pool": {},           # family -> allowed task_ids; missing = every form of it
    "anchor_task": "",         # the one form every participant does identically
    "heldout_task": "",        # kept for the prediction / personalisation evaluation
    "randomization_rule": "latin",     # latin | random | fixed
    "prompt_style_rule": "balanced",   # balanced | random | fixed:<style>
}

DEFAULT_STUDY: Dict[str, Any] = {
    "active": False,
    "study_id": "",
    "tasks": [],               # empty = every enabled task
    "order": "latin",          # latin | random | fixed
    "condition": dict(DEFAULT_CONDITION),
    "groups": {},              # optional between-subject arms: {"A": {...condition overrides}}
    "protocol": dict(DEFAULT_PROTOCOL),
}

CONDITION_KEYS = set(DEFAULT_CONDITION)


def load_study() -> Dict[str, Any]:
    cfg = read_json(STUDY_PATH) or {}
    out = dict(DEFAULT_STUDY)
    out.update({k: v for k, v in cfg.items() if k in DEFAULT_STUDY})
    out["condition"] = {**DEFAULT_CONDITION, **(cfg.get("condition") or {})}
    out["protocol"] = {**DEFAULT_PROTOCOL, **(cfg.get("protocol") or {})}
    return out


def save_study(cfg: Dict[str, Any]) -> Dict[str, Any]:
    merged = load_study()
    merged.update({k: v for k, v in cfg.items() if k in DEFAULT_STUDY})
    merged["condition"] = {**merged["condition"], **{k: v for k, v in (cfg.get("condition") or {}).items() if k in CONDITION_KEYS}}
    merged["protocol"] = {**merged["protocol"], **(cfg.get("protocol") or {})}
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


def roster_entry(participant_id: str) -> Dict[str, Any]:
    return dict(_roster().get((participant_id or "").strip()) or {})


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
    return {"participant_id": pid, "index": rec["index"], "known": True,
            "planned_order": rec.get("planned_order") or [],
            "protocol_id": rec.get("protocol_id", "")}


def freeze_plan(participant_id: str, planned: Dict[str, Any]) -> List[str]:
    """Store the planned order the first time it is computed, and keep it.

    Task order is a confound. If the library or the protocol changes mid-study,
    a recomputed plan would silently disagree with what this child was actually
    walked through — so the first plan wins and later runs compare against it.
    """
    pid = (participant_id or "").strip()
    if not pid:
        return planned.get("planned_order") or []
    roster = _roster()
    rec = roster.get(pid)
    if rec is None:
        return planned.get("planned_order") or []
    if not rec.get("planned_order"):
        rec["planned_order"] = list(planned.get("planned_order") or [])
        rec["protocol_id"] = planned.get("protocol_id", "")
        rec["planned_at"] = now_iso()
        write_json(ROSTER_PATH, roster)
    return rec["planned_order"]


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


# -- protocol: families -> one balanced, reproducible run per participant ----
def _forms_of(family: str, pool: Dict[str, Any]) -> List[str]:
    allowed = pool.get(family)
    if allowed:
        return [t for t in allowed if t in QUESTS_BY_ID]
    return [q["id"] for q in QUESTS if q.get("family") == family]


def _pick_style(forms: List[str], rule: str, index: int) -> List[str]:
    """Keep one form per (family, condition) but rotate `prompt_style` across
    participants, so prompt style is balanced instead of confounded with task."""
    styles = sorted({QUESTS_BY_ID[t].get("prompt_style", "") for t in forms if t in QUESTS_BY_ID})
    if len(styles) <= 1 or rule == "random":
        return forms
    if rule.startswith("fixed:"):
        want = rule.split(":", 1)[1]
    else:                                        # balanced
        want = styles[index % len(styles)]
    kept = [t for t in forms if QUESTS_BY_ID[t].get("prompt_style") == want]
    return kept or forms


def plan(participant_id: str = "", index: Optional[int] = None,
         protocol: Optional[Dict[str, Any]] = None, order: str = "latin") -> Dict[str, Any]:
    """The planned task order for one participant.

    Deterministic in the participant index, so the same code always replays the
    same run — and `planned_order` is stored next to `actual_order` because task
    order is a confound that has to be checkable after the fact, not assumed.
    """
    proto = {**DEFAULT_PROTOCOL, **(protocol or {})}
    idx = index if index is not None else (_seed(participant_id) if participant_id else 0)
    fams = list(proto["required_families"])
    if not fams:
        fams = sorted({QUESTS_BY_ID[t].get("family", "") for t in _forms_of("", {}) } or
                      {q.get("family", "") for q in QUESTS})
    rule = proto.get("randomization_rule") or order

    anchor, heldout = proto.get("anchor_task", ""), proto.get("heldout_task", "")
    # An anchor/held-out task *is* that family's slot for every participant —
    # it replaces the rotated form rather than being added on top of it, or the
    # family would be measured twice and the run would grow by one per fixed task.
    pinned = {QUESTS_BY_ID[t]["family"]: t for t in (anchor, heldout) if t in QUESTS_BY_ID}
    for fam in pinned:
        if fam not in fams:
            fams.append(fam)

    free: List[str] = []
    for i, fam in enumerate(fams):
        if fam in pinned:
            continue
        forms = _pick_style(_forms_of(fam, proto.get("task_pool") or {}),
                            proto.get("prompt_style_rule") or "balanced", idx)
        if forms:
            # rotate which parallel form this participant gets, per family
            free.append(forms[(idx + i) % len(forms)])

    # Counterbalance only the free slots. Ordering all five and then forcing the
    # anchor first and the held-out task last would undo the balance it just
    # computed — the middle positions would stop being uniform.
    ordered = task_sequence(participant_id, free, rule, idx)
    if anchor in QUESTS_BY_ID:
        ordered = [anchor] + ordered              # same first task for everyone
    if heldout in QUESTS_BY_ID:
        ordered = ordered + [heldout]             # always last, held out
    return {"protocol_id": proto.get("protocol_id", ""), "families": fams,
            "planned_order": ordered, "anchor_task": anchor or "", "heldout_task": heldout or "",
            "randomization_rule": rule, "prompt_style_rule": proto.get("prompt_style_rule", "")}


def assign(participant_id: str = "", anon_id: str = "", group: str = "") -> Dict[str, Any]:
    """Everything the client needs to run one participant through the study."""
    study = load_study()
    reg = register_participant(participant_id, anon_id) if study["active"] else {"index": None}
    proto = study.get("protocol") or {}
    if proto.get("required_families") or proto.get("protocol_id"):
        planned = plan(participant_id, reg.get("index"), proto, study["order"])
        if study["active"]:
            planned["planned_order"] = freeze_plan(participant_id, planned)
        seq = planned["planned_order"]
    else:   # no protocol configured: fall back to ordering the listed tasks
        seq = task_sequence(participant_id, study["tasks"], study["order"], reg.get("index"))
        planned = {"protocol_id": "", "planned_order": seq, "families": [],
                   "anchor_task": "", "heldout_task": "",
                   "randomization_rule": study["order"], "prompt_style_rule": ""}
    return {
        "active": study["active"],
        "study_id": study["study_id"],
        "protocol": planned,
        "protocol_id": planned["protocol_id"],
        "planned_order": planned["planned_order"],
        "participant_id": participant_id,
        "participant_index": reg.get("index"),
        "group": group,
        "order": study["order"],
        "sequence": seq,
        "condition": resolve_condition(group=group),
        "assigned_at": now_iso(),
    }
