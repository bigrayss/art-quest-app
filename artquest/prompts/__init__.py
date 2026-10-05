"""模型用的提示词，整份来自用户维护的 docs/art_feedback_prompts_zh_en_v0.3.json（这里是拷贝，
程序只读这份；改提示词改 docs 那份再 `cp` 过来，版本号跟着文件走）。

四段：
* score[dim]   九维逐维打分，一次一个维度，只回一个 1–5 的整数（KidsArtBench 上游原文）
* during       画到一半的陪伴
* review       第一次交卷后的评价（还能改一次）
* final        最终提交后的收尾评价

usage 里说得很清楚：每段都是独立的 system，**不要再拼别的通用提示**；
图要走多模态接口真的传，`<image>` 只是原文里的标记。
"""
import json
import os
import re
from pathlib import Path
from typing import Any, Dict

_FILE = Path(__file__).with_name("art_feedback_v0.3.json")
PROMPTS: Dict[str, Any] = json.loads(_FILE.read_text(encoding="utf-8"))
VERSION: str = PROMPTS.get("prompt_version", "art_feedback_v0.3")
DIM_NAMES: Dict[str, Dict[str, str]] = PROMPTS["dimension_names"]      # lang -> key -> 名字

# 打分用哪种语言的量规。默认英文：那是论文里的原文，中文是译本；
# 而且评分是研究量表，中英会话用同一份才能比。想试中文量规：ARTQUEST_SCORE_PROMPT_LANG=zh
SCORE_PROMPT_LANG = os.environ.get("ARTQUEST_SCORE_PROMPT_LANG", "en").strip().lower() or "en"


def lang_of(quest: Dict[str, Any]) -> str:
    return "en" if quest.get("lang") == "en" else "zh"


def score_prompt(lang: str, dim_key: str) -> str:
    """某一维的完整打分提示，去掉开头的 `<image>` 标记（图单独传）。"""
    text = PROMPTS[lang]["score"][dim_key]
    return re.sub(r"^\s*<image>\s*", "", text)


def system(lang: str, which: str) -> str:
    """during / review / final 三段之一。"""
    return PROMPTS[lang][which]
