"""Runtime configuration (environment-driven, no secrets in code)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = Path(os.environ.get("ARTQUEST_DATA_DIR", BASE_DIR / "data"))
SESSIONS_DIR = DATA_DIR / "sessions"

# How often the browser sends an intermediate canvas image (seconds).
SNAPSHOT_INTERVAL_SEC = int(os.environ.get("ARTQUEST_SNAPSHOT_INTERVAL", "45"))

# Claude settings. Model defaults to Claude Opus 5.
CLAUDE_MODEL = os.environ.get("ARTQUEST_MODEL", "claude-opus-5")
CLAUDE_EFFORT = os.environ.get("ARTQUEST_EFFORT", "medium")

# Backend selection: auto | claude | heuristic (scorer) / auto | claude | template (feedback)
SCORER_BACKEND = os.environ.get("ARTQUEST_SCORER", "auto")
FEEDBACK_BACKEND = os.environ.get("ARTQUEST_FEEDBACK", "auto")


def claude_available() -> bool:
    """True when the Anthropic SDK can find credentials without us passing a key."""
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def resolve_backend(setting: str, ai_name: str, fallback_name: str) -> str:
    if setting == "auto":
        return ai_name if claude_available() else fallback_name
    return setting
