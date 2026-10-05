#!/usr/bin/env python3
"""拿 .env 里配好的模型真打一次，看三件事：文字通不通、图片吃不吃、JSON 能不能要到。

    set -a; . ./.env; set +a; .venv/bin/python tools/try_llm.py [某张画.png]

不传图就画一张带圆和线的小图。四个引擎的提示词原样走一遍（评分 / 反馈 / 陪伴），
所以看到的就是孩子会看到的。不写任何数据。
"""
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw  # noqa: E402

from artquest import config, llm  # noqa: E402


def stat():
    c = llm.LAST_CALL
    if c:
        print(f"      ↳ {c['seconds']}s  tokens in/out {c['prompt_tokens']}/{c['completion_tokens']}  "
              f"思维链 {c['reasoning_chars']} 字  finish={c['finish_reason']}")


def sample_png() -> bytes:
    img = Image.new("RGB", (480, 360), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((60, 60, 260, 260), fill=(250, 200, 80), outline="black", width=5)
    d.line((300, 320, 440, 80), fill=(40, 90, 200), width=8)
    d.rectangle((300, 200, 440, 330), outline=(200, 40, 60), width=4)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def main():
    print(f"provider={config.LLM_PROVIDER} backend={config.LLM_BACKEND} model={config.LLM_MODEL} "
          f"base_url={config.LLM_BASE_URL or '-'} keys={len(config.LLM_API_KEYS)}")
    if not config.llm_available():
        sys.exit("没有 key：先 `set -a; . ./.env; set +a`")
    png = Path(sys.argv[1]).read_bytes() if len(sys.argv) > 1 else sample_png()

    t = time.time()
    print("\n[1] 纯文字 →", repr(llm.claude_text("你只回一个词。", [{"type": "text", "text": "回「通」。"}], 20)),
          f"({time.time() - t:.1f}s)"); stat()

    t = time.time()
    print("\n[2] 看图 →", llm.claude_text("用一句中文说出图里有什么，不评价。",
                                         [llm.image_block(png), {"type": "text", "text": "图里有什么？"}], 100),
          f"({time.time() - t:.1f}s)"); stat()

    quest = {"id": "try", "title": "试一下", "prompt": "随便画一个圆和一条线。", "focus_dims": ["color_contrast", "line_combination"],
             "applicable_dims": ["color_richness", "color_contrast", "line_combination", "line_texture", "picture_organization"],
             "lang": "zh", "ui": "full"}
    intent = {"emotion": "平静", "text": "我想画一个太阳和一根旗杆"}

    from artquest.scoring.claude_scorer import ClaudeScorer
    from artquest.feedback.claude_feedback import ClaudeFeedback
    from artquest.assist.claude_assist import ClaudeAssist

    t = time.time()
    scores = ClaudeScorer().score(png, quest, intent)
    print(f"\n[3] 评分 ({time.time() - t:.1f}s):")
    for k, v in scores["dims"].items():
        print(f"    {k:22s} {v['score']}  {v['note']}")
    print("    summary:", scores["summary"]); stat()

    t = time.time()
    print(f"\n[4] 陪伴 →", ClaudeAssist().assist(png, quest, intent, 1)["text"], f"({time.time() - t:.1f}s)"); stat()

    t = time.time()
    print(f"\n[5] 反馈 ({time.time() - t:.1f}s):\n" + ClaudeFeedback().feedback(png, quest, intent, scores)["text"]); stat()


if __name__ == "__main__":
    main()
