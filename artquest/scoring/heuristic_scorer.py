"""Offline fallback scorer based on simple image statistics.

Only colour, line and layout dimensions carry signal; semantic dimensions
(realism, deformation, imagination, transformation) are returned as a neutral
midpoint and clearly labelled, so nobody mistakes them for a real judgement.
"""
import colorsys
import io
from typing import Any, Dict

from PIL import Image, ImageFilter, ImageStat

from .base import SCALE_MAX, empty_result

NEUTRAL = (1 + SCALE_MAX) / 2


def _clamp(x: float) -> float:
    return round(max(1.0, min(float(SCALE_MAX), x)), 1)


class HeuristicScorer:
    name = "heuristic"

    def score(self, image_png: bytes, quest: Dict[str, Any], intent: Dict[str, Any]) -> Dict[str, Any]:
        img = Image.open(io.BytesIO(image_png)).convert("RGB")
        img.thumbnail((320, 320))
        w, h = img.size
        px = list(img.getdata())

        # --- colour --------------------------------------------------------
        hue_bins, sat_sum, drawn = set(), 0.0, 0
        for r, g, b in px:
            hh, ss, vv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if vv > 0.97 and ss < 0.05:  # white paper
                continue
            drawn += 1
            sat_sum += ss
            if ss > 0.15:
                hue_bins.add(int(hh * 12))
        coverage = drawn / max(1, len(px))
        color_richness = 1 + 9 * min(1.0, len(hue_bins) / 7)
        lum = ImageStat.Stat(img.convert("L"))
        color_contrast = 1 + 9 * min(1.0, lum.stddev[0] / 80)

        # --- lines ---------------------------------------------------------
        edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
        est = ImageStat.Stat(edges)
        edge_density = est.mean[0] / 255
        line_texture = 1 + 9 * min(1.0, est.stddev[0] / 60)
        line_combination = 1 + 9 * min(1.0, edge_density * 12)

        # --- layout: how evenly the drawing occupies a 3x3 grid ------------
        cells = []
        for gy in range(3):
            for gx in range(3):
                box = (gx * w // 3, gy * h // 3, (gx + 1) * w // 3, (gy + 1) * h // 3)
                crop = img.crop(box).convert("L")
                cells.append(sum(1 for v in crop.getdata() if v < 245) / max(1, crop.size[0] * crop.size[1]))
        used = sum(1 for c in cells if c > 0.03)
        centre_weight = cells[4] / max(1e-6, sum(cells))
        picture_organization = 1 + 9 * min(1.0, 0.6 * used / 9 + 0.4 * (1 - abs(centre_weight - 0.2) * 2))

        res = empty_result(self.name)
        res["dims"] = {
            "realism": {"score": NEUTRAL, "note": "启发式无法判断（需模型评分）"},
            "deformation": {"score": NEUTRAL, "note": "启发式无法判断（需模型评分）"},
            "imagination": {"score": NEUTRAL, "note": "启发式无法判断（需模型评分）"},
            "color_richness": {"score": _clamp(color_richness), "note": f"使用了约 {len(hue_bins)} 种色相"},
            "color_contrast": {"score": _clamp(color_contrast), "note": f"明度标准差 {lum.stddev[0]:.0f}"},
            "line_combination": {"score": _clamp(line_combination), "note": f"边缘密度 {edge_density:.2f}"},
            "line_texture": {"score": _clamp(line_texture), "note": "边缘强度变化"},
            "picture_organization": {"score": _clamp(picture_organization), "note": f"九宫格中使用了 {used}/9 格"},
            "transformation": {"score": NEUTRAL, "note": "启发式无法判断（需模型评分）"},
        }
        res["summary"] = f"离线启发式评分：画面覆盖率 {coverage:.0%}，色相 {len(hue_bins)} 种。语义维度为占位值。"
        return res
