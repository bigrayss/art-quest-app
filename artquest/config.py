"""Runtime configuration (environment-driven, no secrets in code)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = Path(os.environ.get("ARTQUEST_DATA_DIR", BASE_DIR / "data"))
SESSIONS_DIR = DATA_DIR / "sessions"
# 账号（孩子自己起的名字 + 暗号摘要）。和 session 分开放：一个是人，一个是作品。
ACCOUNTS_DIR = DATA_DIR / "accounts"

# 研究员令牌。带着它（`Authorization: Bearer …`）才看得到全量列表、能打分、能策展。
# **不设就是关着**：这些接口在公网上一律 401。本机自己看数据，往 .env 里写一行
# `ARTQUEST_ADMIN_TOKEN=随便一串长随机数` 就行（`python3 -c "import secrets;print(secrets.token_urlsafe(24))"`）。
ADMIN_TOKEN = os.environ.get("ARTQUEST_ADMIN_TOKEN", "").strip()

# 允许跨源调 API 的来源。iOS 壳把外壳打进 app 包里，从 `artquest://app` 这个源发请求，
# 浏览器规矩是要服务器点头。网页版和 API 同源，用不到这一条。逗号分隔可加多个。
CORS_ORIGINS = [o.strip() for o in os.environ.get("ARTQUEST_CORS_ORIGINS", "artquest://app").split(",") if o.strip()]

# How often the browser sends an intermediate canvas image (seconds); 0 = never.
# Off by default: Artwork(t) = replay(strokes[0:t], events[0:t]), so a periodic
# PNG is a copy of something the log already contains. Set it only when an
# experiment genuinely needs frames it cannot regenerate.
SNAPSHOT_INTERVAL_SEC = int(os.environ.get("ARTQUEST_SNAPSHOT_INTERVAL", "0"))

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
