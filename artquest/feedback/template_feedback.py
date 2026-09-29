"""Offline feedback built from the intent and the quest's focus dimensions.

话是说给 6–14 岁的孩子听的：一句一个意思，短，不评价。
三段固定开头留着（我看到 / 一个问题 / 可以试试；I see / One question / Try this）。
心情或心愿是空的就不提——「带着「」的心情」那种空壳不许出现。
简单版（quest["ui"] == "simple"）只要「我看到」+「可以试试」两句。
"""
from typing import Any, Dict

from ..scoring.base import DIMENSIONS

_ZH = {d["key"]: d["zh"] for d in DIMENSIONS}
_EN = {d["key"]: d["en"].lower() for d in DIMENSIONS}

# 心情存的是中文词（数据不变），英文会话里说出来时换成英文。
EMOTION_EN = {"开心": "happy", "平静": "calm", "兴奋": "excited", "好奇": "curious", "期待": "hopeful",
              "紧张": "nervous", "难过": "sad", "生气": "angry", "累了": "tired", "难说": "not sure"}


def emotion_en(word: str) -> str:
    return EMOTION_EN.get((word or "").strip(), word or "")


def _clean(text: str) -> str:
    return (text or "").strip().strip("。！!，,、 .")


class TemplateFeedback:
    name = "template"

    def feedback(self, image_png: bytes, quest: Dict[str, Any], intent: Dict[str, Any], scores: Dict[str, Any]) -> Dict[str, Any]:
        focus = quest.get("focus_dims", [])
        dims = scores.get("dims", {})
        ranked = sorted(focus, key=lambda k: dims.get(k, {}).get("score", 5))
        low = ranked[0] if ranked else "imagination"
        simple = quest.get("brief", True)
        wish = _clean(intent.get("text"))
        mood = (intent.get("emotion") or "").strip()

        if quest.get("lang") == "en":
            mood_en = emotion_en(mood) if mood else ""
            if wish and mood_en:
                see = f"I see: you felt {mood_en} and drew “{wish}”."
            elif wish:
                see = f"I see: you drew “{wish}”."
            elif mood_en:
                see = f"I see: you felt {mood_en} while drawing this."
            else:
                see = "I see: you finished a picture."
            if simple:
                text = see + "\nTry this: change one small thing, like a color or a size."
                return {"backend": self.name, "text": text}
            ask = ("One question: can someone see what you wanted, just from the picture?" if wish
                   else "One question: which part do you want people to look at first?")
            text = (f"{see}\n{ask}\n"
                    f"Try this: change one small thing in {_EN.get(low, low)}, like a size, a color or a place. No need to redraw.")
            return {"backend": self.name, "text": text}

        if wish and mood:
            see = f"我看到：你心情{mood}，画的是「{wish}」。"
        elif wish:
            see = f"我看到：你画的是「{wish}」。"
        elif mood:
            see = f"我看到：你心情{mood}，画完了这一幅。"
        else:
            see = "我看到：你画完了这一幅。"
        if simple:
            text = see + "\n可以试试：改一小处，比如一个颜色或大小。"
            return {"backend": self.name, "text": text}
        ask = "一个问题：别人只看画，能看出你想画的吗？" if wish else "一个问题：你最想让人看画里的哪儿？"
        text = (f"{see}\n{ask}\n"
                f"可以试试：在「{_ZH.get(low, low)}」上改一小处，比如大小、颜色或位置。不用重画。")
        return {"backend": self.name, "text": text}

    def compare(self, before_png: bytes, after_png: bytes, before_scores: Dict[str, Any], after_scores: Dict[str, Any],
                quest: Dict[str, Any], intent: Dict[str, Any]) -> Dict[str, Any]:
        bd, ad = before_scores.get("dims", {}), after_scores.get("dims", {})
        deltas = {k: round(ad[k]["score"] - bd[k]["score"], 1) for k in ad if k in bd}
        simple = quest.get("brief", True)
        if quest.get("lang") == "en":
            up_en = [_EN[k] for k, v in deltas.items() if v >= 1]
            text = ("After your change, " + ", ".join(up_en) + " looks different." if up_en
                    else "After your change, the picture looks about the same.")
            if not simple:
                text += " Is it closer to what you wanted?"
            return {"backend": self.name, "text": text}
        up = [_ZH[k] for k, v in deltas.items() if v >= 1]
        text = ("改完以后，" + "、".join(up) + "变了。") if up else "改完以后，变化不大。"
        if not simple:
            text += "你觉得更像你想画的了吗？"
        return {"backend": self.name, "text": text}
