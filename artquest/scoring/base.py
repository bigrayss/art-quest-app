from typing import Any, Dict, List, Protocol

SCALE_MAX = 5  # 1–5; adjust to match the official KidsArtBench scale if it differs

# (key, 中文名, English, one-line rubric used in prompts/UI)
DIMENSIONS: List[Dict[str, str]] = [
    {"key": "realism", "zh": "写实", "en": "Realism", "desc": "物体、比例、空间关系是否接近真实观察"},
    {"key": "deformation", "zh": "变形", "en": "Deformation", "desc": "是否有意识地夸张、扭曲或简化形体来表达"},
    {"key": "imagination", "zh": "想象", "en": "Imagination", "desc": "内容、情境、设定的新颖与独特程度"},
    {"key": "color_richness", "zh": "色彩丰富", "en": "Color Richness", "desc": "颜色种类、层次与变化"},
    {"key": "color_contrast", "zh": "色彩对比", "en": "Color Contrast", "desc": "明暗、冷暖、互补等对比的运用"},
    {"key": "line_combination", "zh": "线条组合", "en": "Line Combination", "desc": "线条之间的组织、疏密与节奏"},
    {"key": "line_texture", "zh": "线条质感", "en": "Line Texture", "desc": "线条的力度、粗细变化与肌理"},
    {"key": "picture_organization", "zh": "画面组织", "en": "Picture Organization", "desc": "构图、主次、平衡与视线引导"},
    {"key": "transformation", "zh": "转化", "en": "Transformation", "desc": "把熟悉事物转化为新形象、新功能或新故事的程度"},
]
DIM_KEYS = [d["key"] for d in DIMENSIONS]


class Scorer(Protocol):
    name: str

    def score(self, image_png: bytes, quest: Dict[str, Any], intent: Dict[str, Any]) -> Dict[str, Any]:
        """Return {"backend", "scale", "dims": {key: {"score", "note"}}, "summary"}."""
        ...


def empty_result(backend: str) -> Dict[str, Any]:
    return {"backend": backend, "scale": [1, SCALE_MAX], "dims": {}, "summary": ""}
