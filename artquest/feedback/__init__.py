"""AI text feedback (Stage 1 = Level 1 of the AI Visual Coach).

Principles from the guide §05: AI helps thinking, never replaces creation;
prefer prompts, comparisons and questions; no "standard answer"; scores must
not dominate the child's attention.
"""
from ..config import FEEDBACK_BACKEND, resolve_backend


def get_feedback_engine():
    backend = resolve_backend(FEEDBACK_BACKEND, "claude", "template")
    if backend == "claude":
        from .claude_feedback import ClaudeFeedback
        return ClaudeFeedback()
    from .template_feedback import TemplateFeedback
    return TemplateFeedback()
