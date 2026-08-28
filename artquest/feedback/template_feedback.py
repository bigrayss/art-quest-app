"""Offline feedback built from the intent and the quest's focus dimensions."""
from typing import Any, Dict

from ..scoring.base import DIMENSIONS

_ZH = {d["key"]: d["zh"] for d in DIMENSIONS}


class TemplateFeedback:
    name = "template"

    def feedback(self, image_png: bytes, quest: Dict[str, Any], intent: Dict[str, Any], scores: Dict[str, Any]) -> Dict[str, Any]:
        focus = quest.get("focus_dims", [])
        dims = scores.get("dims", {})
        ranked = sorted(focus, key=lambda k: dims.get(k, {}).get("score", 5))
        low = ranked[0] if ranked else "imagination"
        wish = intent.get("text") or "你想表达的东西"
        text = (
            f"我看到：你带着「{intent.get('emotion', '某种')}」的心情画了这幅画，想表达的是——{wish}。\n"
            f"一个问题：如果只看画面，一个不认识你的人能感受到这一点吗？哪个部分最能说明它？\n"
            f"可以试试：围绕「{_ZH.get(low, low)}」再做一点尝试，比如改变一处大小、颜色或位置，看看感觉有没有变化。"
            "不需要重画，改一小处就可以。"
        )
        return {"backend": self.name, "text": text}

    def compare(self, before_png: bytes, after_png: bytes, before_scores: Dict[str, Any], after_scores: Dict[str, Any],
                quest: Dict[str, Any], intent: Dict[str, Any]) -> Dict[str, Any]:
        bd, ad = before_scores.get("dims", {}), after_scores.get("dims", {})
        deltas = {k: round(ad[k]["score"] - bd[k]["score"], 1) for k in ad if k in bd}
        up = [f"{_ZH[k]}" for k, v in deltas.items() if v >= 1]
        text = "修改后，" + ("在" + "、".join(up) + "上有了变化。" if up else "整体变化不大。")
        text += " 你自己觉得，改完以后更接近一开始想表达的感觉了吗？"
        return {"backend": self.name, "text": text}
