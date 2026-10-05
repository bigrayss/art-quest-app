"""Runtime configuration (environment-driven, no secrets in code)."""
import json
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


def teacher_code() -> str:
    """老师注册要的邀请码。没设就是不开放老师注册。每次读环境，测试里改得动。"""
    return os.environ.get("ARTQUEST_TEACHER_CODE", "").strip()

# 允许跨源调 API 的来源。iOS 壳把外壳打进 app 包里，从 `artquest://app` 这个源发请求，
# 浏览器规矩是要服务器点头。网页版和 API 同源，用不到这一条。逗号分隔可加多个。
CORS_ORIGINS = [o.strip() for o in os.environ.get("ARTQUEST_CORS_ORIGINS", "artquest://app").split(",") if o.strip()]

# How often the browser sends an intermediate canvas image (seconds); 0 = never.
# Off by default: Artwork(t) = replay(strokes[0:t], events[0:t]), so a periodic
# PNG is a copy of something the log already contains. Set it only when an
# experiment genuinely needs frames it cannot regenerate.
SNAPSHOT_INTERVAL_SEC = int(os.environ.get("ARTQUEST_SNAPSHOT_INTERVAL", "0"))

# ---- 模型后端 ----------------------------------------------------------------
# 两条通路，提示词、输出格式、记录字段全都一样，只是换了谁来答：
#   anthropic  Anthropic SDK（ANTHROPIC_API_KEY）
#   openai     任何 OpenAI 兼容接口（ARTQUEST_LLM_BASE_URL + ARTQUEST_LLM_API_KEY），
#              比如华东师大的 ecnu-plus：https://chat.ecnu.edu.cn/open/api/v1
# 不写 ARTQUEST_LLM_PROVIDER 就按给了哪种 key 自动选；两种都给，openai 优先（大陆服务器只有它通）。
LLM_BASE_URL = os.environ.get("ARTQUEST_LLM_BASE_URL", "").strip().rstrip("/")
LLM_API_KEY = os.environ.get("ARTQUEST_LLM_API_KEY", "").strip()
_provider = os.environ.get("ARTQUEST_LLM_PROVIDER", "").strip().lower()
if not _provider:
    _provider = "openai" if (LLM_BASE_URL and LLM_API_KEY) else "anthropic"
LLM_PROVIDER = _provider

# 模型名。anthropic 默认 Opus 5；openai 通路必须自己写（ecnu-plus）。
_default_model = "claude-opus-5" if LLM_PROVIDER == "anthropic" else "ecnu-plus"
LLM_MODEL = os.environ.get("ARTQUEST_MODEL", _default_model)
# Claude 的 effort；openai 通路上映射成 reasoning_effort（只在 ARTQUEST_LLM_THINKING=1 时送）。
LLM_EFFORT = os.environ.get("ARTQUEST_EFFORT", "medium")
# openai 通路要不要开思维链。默认关：给孩子的一两句话要快，评分的 JSON 也不靠它。
LLM_THINKING = os.environ.get("ARTQUEST_LLM_THINKING", "0").strip().lower() in ("1", "true", "yes", "on")
LLM_TIMEOUT_SEC = float(os.environ.get("ARTQUEST_LLM_TIMEOUT", "90"))
# 试参数的后门：一段 JSON，原样并进 openai 通路的请求体。比如想试 Qwen 原生的关思考写法：
#   ARTQUEST_LLM_EXTRA={"chat_template_kwargs":{"enable_thinking":false}}
try:
    LLM_EXTRA = json.loads(os.environ.get("ARTQUEST_LLM_EXTRA") or "{}")
    if not isinstance(LLM_EXTRA, dict):
        raise ValueError("not an object")
except ValueError as _e:
    LLM_EXTRA = {}

# 记录里 `backend` 字段写的名字。评分 / 反馈 / 陪伴三处都用它，分析时一眼看出是哪家模型答的。
# anthropic → claude；ecnu 的地址 → ecnu；别的 OpenAI 兼容服务 → openai。可用 ARTQUEST_LLM_NAME 覆盖。
_default_name = "claude" if LLM_PROVIDER == "anthropic" else ("ecnu" if "ecnu" in LLM_BASE_URL else "openai")
LLM_BACKEND = os.environ.get("ARTQUEST_LLM_NAME", _default_name).strip() or _default_name

# 旧名字，别的模块还在引
CLAUDE_MODEL = LLM_MODEL
CLAUDE_EFFORT = LLM_EFFORT

# Backend selection: auto | llm | heuristic (scorer) / auto | llm | template (feedback)
# `llm` 就是「用上面配好的模型」；`claude` / `ecnu` / `ai` 都当 `llm` 的别名收，老 .env 不用改。
SCORER_BACKEND = os.environ.get("ARTQUEST_SCORER", "auto")
FEEDBACK_BACKEND = os.environ.get("ARTQUEST_FEEDBACK", "auto")
_LLM_ALIASES = {"llm", "ai", "claude", "ecnu", "openai"}


def llm_available() -> bool:
    """True when the configured provider has credentials."""
    if LLM_PROVIDER == "openai":
        return bool(LLM_BASE_URL and LLM_API_KEY)
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


claude_available = llm_available   # 旧名字


def resolve_backend(setting: str, ai_name: str, fallback_name: str) -> str:
    """Return `ai_name` when the model should answer, else `fallback_name`."""
    if setting == "auto":
        return ai_name if llm_available() else fallback_name
    if setting in _LLM_ALIASES:
        return ai_name
    return setting
