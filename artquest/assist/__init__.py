"""创作**进行中**的陪伴（对应指南 §05 的 Level 1，但位置不同）。

和 `feedback` 包的分工是硬的，别混：

- `feedback` 在**交卷之后**说话，看得到九维分数，可以谈作品。
- `assist` 在**画到一半**说话，只鼓励和发问，**不评价质量**。

后者的理由是项目一贯的那条原则——不给孩子下判决。创作过程中一旦听到
「树画得有点小」，孩子接下来画的就不是他想画的，而是他猜 AI 想要的；
表达当场变成迎合。评价属于交卷之后，那时它才不会改写正在发生的创作。

和 feedback 一样：没有 API key 也要能跑，走模板版。
"""
from ..config import FEEDBACK_BACKEND, resolve_backend


def get_assist_engine():
    """和 feedback 共用一个后端开关——它们是同一件事的两个时机，
    没有「反馈用 AI 但陪伴用模板」这种配置需求。"""
    backend = resolve_backend(FEEDBACK_BACKEND, "claude", "template")
    if backend == "claude":
        from .claude_assist import ClaudeAssist
        return ClaudeAssist()
    from .template_assist import TemplateAssist
    return TemplateAssist()
