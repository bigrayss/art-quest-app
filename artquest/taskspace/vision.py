# -*- coding: utf-8 -*-
"""视觉判断器：把材料检查里「需要看图」的问题交给支持图片的模型（ecnu-plus 走 artquest.llm 的 openai 通路）。

状态分四种，不互相冒充：
    request_failed   请求没成功（网络 / 401 / 429 / 5xx）
    parse_failed     回了东西但不是约定的 JSON
    无法判断          模型自己说看不清
    符合 / 不符合     模型的判断
返回给 check_material 的只有后三种里的「符合 / 不符合 / 无法判断」；前两种在 `last_errors` 里另记，
**不映射成「无法判断」**——否则接口坏了和模型真不确定分不开。

接之前先跑 `probe()`：两张对象位置相反的图，同一个不泄露答案的问题，答案必须随图变化。
"""
import base64
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..llm import LLMBadOutput, llm_json

_SYSTEM = ("你在检查一张给孩子看的参考图是否满足研究者写的条件。只看图回答，不猜、不补。"
           "答案用 JSON：{\"answer\": \"yes\"|\"no\"|\"unsure\", \"evidence\": \"你在图里看到了什么\"}。看不清就 unsure。")
_SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}, "evidence": {"type": "string"}}, "required": ["answer"]}
_MAP = {"yes": "符合", "no": "不符合", "unsure": "无法判断"}


def _image_block(path: Path) -> Dict[str, Any]:
    data = path.read_bytes()
    mt = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return {"type": "image", "source": {"type": "base64", "media_type": mt, "data": base64.standard_b64encode(data).decode("ascii")}}


class VisualJudge:
    def __init__(self) -> None:
        self.last_errors: List[Dict[str, Any]] = []
        self.calls = 0

    def __call__(self, path: Path, question: str) -> str:
        self.calls += 1
        try:
            obj = llm_json(_SYSTEM, [_image_block(Path(path)), {"type": "text", "text": question}], _SCHEMA, max_tokens=300)
        except LLMBadOutput as e:
            self.last_errors.append(dict(path=str(path), question=question, kind="parse_failed", error=str(e)))
            raise
        except Exception as e:      # 网络 / 鉴权 / 限流
            self.last_errors.append(dict(path=str(path), question=question, kind="request_failed", error=str(e)))
            raise
        return _MAP.get(str(obj.get("answer", "")).lower(), "无法判断")


def probe(judge: Callable[[Path, str], str], tmp_dir: Path) -> Dict[str, Any]:
    """最小检查：画两张图，圆在方块左 / 右，问同一个问题「圆在方块的左边吗」，答案必须相反。"""
    from PIL import Image, ImageDraw
    tmp_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, cx in (("left", 60), ("right", 196)):
        im = Image.new("RGB", (256, 128), "white")
        d = ImageDraw.Draw(im)
        d.rectangle((108, 34, 148, 94), fill="#3366cc")
        d.ellipse((cx - 24, 40, cx + 24, 88), fill="#cc3333")
        p = tmp_dir / f"probe_{name}.png"
        im.save(p)
        paths.append(p)
    q = "图里的红色圆形是否在蓝色方块的左边？"
    a_left, a_right = judge(paths[0], q), judge(paths[1], q)
    return dict(left=a_left, right=a_right, ok=(a_left == "符合" and a_right == "不符合"))
