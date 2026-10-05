"""Personalisation arms: No History / User History / Personalized Model.

Selected by the session's frozen `history_mode` condition, so the arm is a
recorded variable like every other condition — never an unlogged difference.

Stage 1 needs no live model: the `history` arm is a template over the
representation and runs offline. The `personalized` arm is wired the same way,
so plugging a real model in is one registration. If it is requested but cannot
run (no API key), the request is served by the template arm **and the record
says so** (`requested_mode` != `backend`, `available: false`) — a silently
downgraded condition would quietly ruin the comparison.
"""
import logging
from typing import Any, Dict, Optional

from ..config import llm_available
from .base import MODES, PREDICTED_KEYS, Personalizer

# Backends are imported inside get_personalizer(), like scoring/ and feedback/:
# importing them here would pull `storage` in at package-import time, and
# unittest discovery imports every package __init__ before the test environment
# has pointed the data dir at a throwaway directory.

log = logging.getLogger("artquest")


def get_personalizer(mode: str = "none") -> Personalizer:
    mode = mode if mode in MODES else "none"
    if mode == "none":
        from .no_history import NoHistory
        return NoHistory()
    from .own_history import OwnHistory
    if mode == "history":
        return OwnHistory()
    if llm_available():
        try:
            from .claude_personalizer import ClaudePersonalizer
            return ClaudePersonalizer()
        except Exception:                      # SDK missing or import failure
            log.exception("claude personalizer unavailable")
    return OwnHistory(requested="personalized",
                      note="no model backend configured; served by the template arm")


__all__ = ["MODES", "PREDICTED_KEYS", "Personalizer", "get_personalizer"]
