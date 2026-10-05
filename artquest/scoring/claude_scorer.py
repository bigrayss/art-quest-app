"""模型打九维分：v0.3 的做法是**一次一个维度**，每维一段完整量规，只回一个 1–5 的整数。

九个维度并行发，总耗时约等于一次调用。只问任务能考察的维度（`applicable_dims`）：
考不到的维度不该有数字，一个硬凑的数和真低分分不开（rubric.apply_contract 再兜一道）。
分数没有说明文字（note 留空）——量规本身就是说明，反馈那段只拿数字。
"""
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from ..config import LLM_BACKEND
from ..llm import LLMBadOutput, claude_text, image_block
from ..prompts import SCORE_PROMPT_LANG, VERSION, score_prompt
from .base import DIM_KEYS, SCALE_MAX, empty_result

log = logging.getLogger("artquest")
_DIGIT = re.compile(r"[1-5]")


def parse_score(reply: str) -> Optional[int]:
    """回复里第一个 1–5。模型偶尔会写「分数：4」或「4/5」，都认；没有数字就是没答。"""
    m = _DIGIT.search(reply or "")
    return int(m.group()) if m else None


class ClaudeScorer:
    name = LLM_BACKEND   # claude / ecnu / …，跟环境变量里配的提供方走

    def score(self, image_png: bytes, quest: Dict[str, Any], intent: Dict[str, Any]) -> Dict[str, Any]:
        keys = [k for k in DIM_KEYS if k in (quest.get("applicable_dims") or DIM_KEYS)]
        img = image_block(image_png)

        def one(key: str) -> Optional[int]:
            content = [img, {"type": "text", "text": score_prompt(SCORE_PROMPT_LANG, key)}]
            last = ""
            for _ in range(2):                       # 没回数字就再要一次
                try:
                    last = claude_text("", content, max_tokens=32)
                except Exception as e:               # 一维挂了（限流、超时）不拖垮整次：这一维留空
                    log.warning("score %s: call failed: %s", key, str(e)[:160])
                    return None
                n = parse_score(last)
                if n is not None:
                    return n
            log.warning("score %s: no digit in reply %r", key, last[:80])
            return None

        # 并发由 llm._GATE 统一管（网关每模型 5 路）；这里的线程数只是上限
        with ThreadPoolExecutor(max_workers=min(9, len(keys)) or 1) as ex:
            results = dict(zip(keys, ex.map(one, keys)))

        out = empty_result(self.name)
        out["dims"] = {k: {"score": n, "note": ""} for k, n in results.items() if n is not None}
        out["prompt_version"] = VERSION
        out["scale"] = [1, SCALE_MAX]
        if not out["dims"]:
            raise LLMBadOutput("no dimension received a score")
        return out
