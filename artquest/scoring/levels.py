# -*- coding: utf-8 -*-
"""KidsArtBench 九维评分量表——给老师看的参考，不是给模型的提示词。

来源：Ye et al., *KidsArtBench: Multi-Dimensional Children's Art Evaluation with
Attribute-Aware MLLMs*, EACL 2026（arXiv:2512.12503）附录 A.1 表 3–11，
以及 github.com/bigrayss/KidsArtBench 的 experiments/utils/prompt_lib.py。
英文是论文原文，一个词没改；中文是照着译的，给老师快速读。

`REFERENCE_DISTRIBUTION` 是仓库 ArtEduDataset/{train,test}.csv 里 1,046 幅作品的
专家终评分布（12 位美术教师、两人独立打分、资深专家仲裁）。它回答老师最常问的
一句「这个维度大家一般打几分」：写实一栏几乎全是 1–2，想象几乎全是 5——
这不是量表出了错，是儿童画的常态。老师照着这个分布校准自己的手，不必和它一样。

评语的例子：公开仓库不含评语文本（论文说明评语只覆盖一部分作品，且随图片
一起走数据使用协议）。下面 `EXAMPLES` 是按论文对「formative comment」的要求
（对着量表说、说给孩子听、指出下一步）写的示范，不是数据集标注。
"""
from typing import Any, Dict, List

SOURCE = {
    "title": "KidsArtBench: Multi-Dimensional Children's Art Evaluation with Attribute-Aware MLLMs",
    "authors": "Mingrui Ye, Chanjin Zheng, Zengyi Yu, Chenyu Xiang, Zhixue Zhao, Zheng Yuan, Helen Yannakoudakis",
    "venue": "EACL 2026",
    "arxiv": "https://arxiv.org/abs/2512.12503",
    "code": "https://github.com/bigrayss/KidsArtBench",
    "n_artworks": 1046, "ages": "5–15", "n_raters": 12,
}

# 四组九维：论文图 2 的分组。顺序和 scoring/base.py 的 DIMENSIONS 一致。
CATEGORIES: List[Dict[str, Any]] = [
    {"key": "formative", "zh": "造型创造力", "en": "Formative Creativity",
     "dims": ["realism", "deformation", "imagination"]},
    {"key": "color", "zh": "色彩表现力", "en": "Color Expressiveness",
     "dims": ["color_richness", "color_contrast"]},
    {"key": "line", "zh": "线条丰富度", "en": "Line Work Richness",
     "dims": ["line_combination", "line_texture"]},
    {"key": "concept", "zh": "概念思维", "en": "Conceptual Thinking",
     "dims": ["picture_organization", "transformation"]},
]

# 每维：criterion 是论文给这一维的一句定义；levels 从 5 到 1。
RUBRIC: Dict[str, Dict[str, Any]] = {
    "realism": {
        "criterion": {
            "zh": "看比例、质感、光影和透视是否准确，画得像不像真的。",
            "en": "This criterion assesses the accuracy of proportions, textures, lighting, and perspective to create a lifelike depiction.",
        },
        "levels": {
            5: {"zh": "写实细节极其精确。质感和光影运用娴熟，比例与透视准确，画面逼真，显示出高超的写实功力。",
                "en": "The artwork exhibits exceptional detail and precision in depicting Realism features. Textures and lighting are used masterfully to mimic real-life appearances with accurate proportions and perspective. The representation is strikingly lifelike, demonstrating advanced skills in realism."},
            4: {"zh": "对象刻画细致、准确。比例和质感处理得很好，光影增强了真实感；透视或细节上可能有小出入。",
                "en": "The artwork presents a high level of detail and accuracy in the portrayal of subjects. Proportions and textures are very well executed, and the lighting enhances the realism. Although highly Realism, minor discrepancies in perspective or detail might be noticeable."},
            3: {"zh": "写实程度中等。基本比例正确，用了一些质感和光影；某些地方缺少纵深或细节。",
                "en": "The artwork represents subjects with a moderate level of realism. Basic proportions are correct, and some textures and lighting effects are used to enhance realism. However, the depiction may lack depth or detail in certain areas."},
            2: {"zh": "有写实的尝试，但比例和质感把握不住。光影、透视时有时无，不太可信。",
                "en": "The artwork attempts realism but struggles with accurate proportions and detailed textures. Lighting and perspective may be inconsistently applied, resulting in a less convincing depiction."},
            1: {"zh": "几乎不顾写实细节。比例、质感、光影都很弱，离真实很远。",
                "en": "The artwork shows minimal attention to Realism details. Proportions, textures, and lighting are poorly executed, making the depiction far from lifelike."},
        },
    },
    "deformation": {
        "criterion": {
            "zh": "看作者能否有意识地、有创意地改变现实的样子，来传达信息、情绪或想法。",
            "en": "This criterion evaluates the artist's ability to creatively and intentionally deform reality to convey a message, emotion, or concept.",
        },
        "levels": {
            5: {"zh": "变形用得炉火纯青，直接强化了情绪或概念。每处变形都有想法、和主题一体，和构图融为一体，打动人。",
                "en": "The artwork demonstrates masterful use of deformation to enhance the emotional or conceptual impact of the piece. The transformations are thoughtful and integral to the artwork's message, seamlessly blending with the composition to engage viewers profoundly."},
            4: {"zh": "变形有效地表达了作者意图。改动融入画面，明显帮助观众理解或产生情绪；个别地方略减效果。",
                "en": "The artwork effectively uses deformation to express artistic intentions. The modifications are well-integrated and contribute significantly to the viewer's understanding or emotional response. Minor elements of the deformation might detract from its overall effectiveness."},
            3: {"zh": "有看得出的变形，为表现加了分。大体贴合主题，但和构图有些脱节，效果参差。",
                "en": "The artwork includes noticeable deformations that add to its artistic expression. While these elements generally support the artwork's theme, they may be somewhat disjointed from the composition, offering mixed impact on the viewer."},
            2: {"zh": "尝试了变形但效果有限。变形显得生硬、浮于表面，对表达帮助不大。",
                "en": "The artwork attempts to use deformation but does so with limited success. The deformations are present but feel forced or superficial, only marginally contributing to the artwork's expressive goals."},
            1: {"zh": "几乎没有变形，或变形无效。看不出它和画面想说的话有什么关系。",
                "en": "The artwork features minimal or ineffective deformation, with little to no enhancement of the artwork's message or emotional impact. The attempts at deformation seem disconnected from the artwork's overall intent."},
        },
    },
    "imagination": {
        "criterion": {
            "zh": "看作者能否用创造力形成独特、原创的想法。",
            "en": "This criterion evaluates the artist's ability to use their creativity to form unique and original ideas within their artwork.",
        },
        "levels": {
            5: {"zh": "原创性和创造力极强，提出了独一无二的概念或解读，既出人意料又引人思考。",
                "en": "The artwork displays a profound level of originality and creativity, introducing unique concepts or interpretations that are both surprising and thought-provoking."},
            4: {"zh": "想法原创且完成得好，但可能和常见主题相近。",
                "en": "The artwork presents creative ideas that are both original and nicely executed, though they may be similar to conventional themes."},
            3: {"zh": "有一些创意，但比较可预期，没有离开常规做法太远。",
                "en": "The artwork shows some creative ideas, but they are somewhat predictable and do not stray far from traditional approaches."},
            2: {"zh": "创意元素很少，想法大多是照搬的，缺少原创。",
                "en": "The artwork has minimal creative elements, with ideas that are largely derivative and lack originality."},
            1: {"zh": "缺少想象，看不到任何原创想法或创意。",
                "en": "The artwork lacks imagination, with no discernible original ideas or creative concepts."},
        },
    },
    "color_richness": {
        "criterion": {
            "zh": "看颜色的运用和范围，画面是否因此好看、耐看。",
            "en": "This criterion assesses the use and range of colors to create a visually engaging experience.",
        },
        "levels": {
            5: {"zh": "用色宽广而和谐，每种颜色都让画面更鲜活、更有动感。",
                "en": "The artwork uses a wide and harmonious range of colors, each contributing to a vivid and dynamic composition."},
            4: {"zh": "颜色种类丰富、搭配均衡，提升了画面的观感。",
                "en": "The artwork features a good variety of colors that are well-balanced, enhancing the visual appeal of the piece."},
            3: {"zh": "颜色种类中等，但配色未必能充分衬托主题。",
                "en": "The artwork includes a moderate range of colors, but the palette may not fully enhance the subject matter."},
            2: {"zh": "颜色种类有限，配色对画面帮助不大。",
                "en": "The artwork has limited color variety, with a palette that does not significantly contribute to the piece's impact."},
            1: {"zh": "用色很差，范围极窄，拖累了观感。",
                "en": "The artwork shows poor use of colors, with a very restricted range that detracts from the visual experience."},
        },
    },
    "color_contrast": {
        "criterion": {
            "zh": "看对比色用得好不好，能不能加强表现力。",
            "en": "This criterion evaluates the effective use of contrasting colors to enhance artistic expression.",
        },
        "levels": {
            5: {"zh": "对比色运用娴熟，视觉冲击强烈而有效。",
                "en": "The artwork masterfully employs contrasting colors to create a striking and effective visual impact."},
            4: {"zh": "对比色用得有效，提升了画面的趣味；对比可能不算强烈。",
                "en": "The artwork effectively uses contrasting colors to enhance visual interest, though the contrast may be less pronounced."},
            3: {"zh": "有一些色彩对比，但没有真正用来提升画面。",
                "en": "The artwork has some contrast in colors, but it is not used effectively to enhance the artwork's overall appeal."},
            2: {"zh": "几乎没用色彩对比，画面平淡。",
                "en": "The artwork makes minimal use of color contrast, resulting in a lackluster visual impact."},
            1: {"zh": "缺少有效的色彩对比，画面没有吸引力。",
                "en": "The artwork lacks effective color contrast, making the piece visually unengaging."},
        },
    },
    "line_combination": {
        "criterion": {
            "zh": "看线条之间怎样组织、怎样互相配合。",
            "en": "This criterion assesses the integration and interaction of lines within the artwork.",
        },
        "levels": {
            5: {"zh": "线条组合极其融洽，形成和谐、引人的视觉流动。",
                "en": "The artwork exhibits exceptional integration of line combinations, creating a harmonious and engaging visual flow."},
            4: {"zh": "线条组合运用得好，支撑起整体构图；局部略欠连贯。",
                "en": "The artwork displays good use of line combinations that contribute to the overall composition, though some areas may lack cohesion."},
            3: {"zh": "线条组合一般，有些段落有效，整体不够连贯。",
                "en": "The artwork shows average use of line combinations, with some effective sections but overall lacking in cohesiveness."},
            2: {"zh": "线条组合几乎不起作用，线条常常互相打架，拼不成一个整体。",
                "en": "The artwork has minimal effective use of line combinations, with lines that often clash or do not contribute to a unified composition."},
            1: {"zh": "线条组织很差，组合破坏了画面的和谐。",
                "en": "The artwork shows poor integration of lines, with combinations that disrupt the visual harmony of the piece."},
        },
    },
    "line_texture": {
        "criterion": {
            "zh": "看线条质感的种类多不多、画得好不好。",
            "en": "This criterion evaluates the variety and execution of line textures within the artwork.",
        },
        "levels": {
            5: {"zh": "线条质感种类丰富，每一种都画得娴熟，提升了画面的美感和主题。",
                "en": "The artwork demonstrates a wide variety of line textures, each skillfully executed to enhance the piece's aesthetic and thematic elements."},
            4: {"zh": "线条质感种类不少、画得好，个别地方不够清晰。",
                "en": "The artwork includes a good range of line textures, well executed but with some areas that may lack definition."},
            3: {"zh": "线条质感种类中等，画得还可以，但缺少细节。",
                "en": "The artwork features moderate variety in line textures, with generally adequate execution but lacking in detail."},
            2: {"zh": "线条质感有限，画法对作品质量没什么帮助。",
                "en": "The artwork has limited line textures, with execution that does not significantly contribute to the artwork's quality."},
            1: {"zh": "线条质感单一、粗糙，画面显得呆板。",
                "en": "The artwork lacks variety and sophistication in line textures, resulting in a visually dull piece."},
        },
    },
    "picture_organization": {
        "criterion": {
            "zh": "看整体构图和空间安排。",
            "en": "This criterion evaluates the overall composition and spatial arrangement within the artwork.",
        },
        "levels": {
            5: {"zh": "组织无可挑剔，每个元素都放得有讲究，构图均衡而有力。",
                "en": "The artwork is impeccably organized, with each element thoughtfully placed to create a balanced and compelling composition."},
            4: {"zh": "组织良好，构图安排得当，能引导视线；个别元素略打断节奏。",
                "en": "The artwork has a good organization, with a well-arranged composition that effectively guides the viewer's eye, though minor elements may disrupt the flow."},
            3: {"zh": "组织尚可，但构图有些失衡或松散。",
                "en": "The artwork has an adequate organization, but the composition may feel somewhat unbalanced or disjointed."},
            2: {"zh": "组织较差，构图缺少条理，抓不住观众。",
                "en": "The artwork shows poor organization, with a composition that lacks coherence and does not effectively engage the viewer."},
            1: {"zh": "组织混乱，构图杂乱，拖累整体效果。",
                "en": "The artwork is poorly organized, with a chaotic composition that detracts from the piece's overall impact."},
        },
    },
    "transformation": {
        "criterion": {
            "zh": "看作者能否把传统的、熟悉的东西变成新的、意想不到的东西。",
            "en": "This criterion assesses the artist's ability to transform traditional or familiar elements into something new and unexpected.",
        },
        "levels": {
            5: {"zh": "彻底的转化：对熟悉元素给出新鲜、有创意的诠释，大大丰富了观感。",
                "en": "The artwork is transformative, offering a fresh and innovative take on traditional elements, significantly enhancing the viewer's experience."},
            4: {"zh": "成功转化了熟悉元素，给出新视角，但创新不算惊人。",
                "en": "The artwork successfully transforms familiar elements, providing a new perspective, though the innovation may not be striking."},
            3: {"zh": "对熟悉元素有一些转化，但改法比较可预期，创新不高。",
                "en": "The artwork shows some transformation of familiar elements, but the changes are somewhat predictable and not highly innovative."},
            2: {"zh": "尝试了转化但收效甚微，改动太细微或没做到位。",
                "en": "The artwork attempts transformation but achieves only minimal success, with changes that are either too subtle or not effectively executed."},
            1: {"zh": "没有转化，传统元素照搬，没有创新或再诠释。",
                "en": "The artwork lacks transformation, with traditional elements that are replicated without any significant innovation or creative reinterpretation."},
        },
    },
}

# 1,046 幅作品的专家终评：每维 1→5 各多少幅。算自仓库 ArtEduDataset/{train,test}.csv，2026-09-30。
REFERENCE_DISTRIBUTION: Dict[str, Dict[str, Any]] = {
    "realism": {"n": 1046, "mean": 1.45, "counts": [602, 419, 25, 0, 0]},
    "deformation": {"n": 1046, "mean": 3.77, "counts": [1, 12, 227, 790, 16]},
    "imagination": {"n": 1046, "mean": 4.70, "counts": [0, 0, 5, 305, 736]},
    "color_richness": {"n": 1046, "mean": 3.69, "counts": [17, 34, 363, 470, 162]},
    "color_contrast": {"n": 1046, "mean": 3.55, "counts": [14, 51, 404, 498, 79]},
    "line_combination": {"n": 1046, "mean": 3.15, "counts": [1, 93, 710, 230, 12]},
    "line_texture": {"n": 1046, "mean": 2.73, "counts": [1, 414, 511, 108, 12]},
    "picture_organization": {"n": 1046, "mean": 3.19, "counts": [1, 61, 724, 260, 0]},
    "transformation": {"n": 1046, "mean": 3.86, "counts": [1, 4, 235, 704, 102]},
}

# 论文对老师打分流程的描述，老师读一遍就知道自己在做什么样的事。
PROCEDURE = {
    "zh": [
        "每幅作品由至少两位受过培训的美术教师独立打分，九个维度各 1–5 分。",
        "分歧由一位资深专家仲裁，必要时回访原打分人，定出每维的终评。",
        "打分人是 12 位教龄 5 年以上的美术教师，平均培训 24 小时。",
        "一部分作品另附教师评语，评语对着量表说，是给孩子的形成性反馈。",
    ],
    "en": [
        "Each artwork was independently scored by at least two trained art educators on nine dimensions, 1–5 each.",
        "A senior expert adjudicated discrepancies, consulting the original raters when necessary, to assign a final score per dimension.",
        "The raters were 12 art educators with more than 5 years' experience, calibrated for 24 hours on average.",
        "A subset of artworks also carries expert-written formative comments aligned with the rubric.",
    ],
}

# 评语示范。评语是写给孩子的：先说看到了什么，再说哪一维用了什么办法，最后给一个能做的下一步。
# 不打总分、不比较别的孩子。中英各一份，不是互译。
EXAMPLES: List[Dict[str, Any]] = [
    {
        "key": "demo",
        "image": "/static/refs/kidsartbench-demo.jpg",
        "caption": {"zh": "KidsArtBench 仓库里的示例图（README 的 demo.png）。分数和评语是本界面写的示范，不是数据集标注。",
                    "en": "The sample artwork from the KidsArtBench repository (demo.png in its README). Scores and comment below are written for this screen, not taken from the dataset."},
        "scores": {"realism": 1, "deformation": 4, "imagination": 5, "color_richness": 4, "color_contrast": 4,
                   "line_combination": 3, "line_texture": 3, "picture_organization": 3, "transformation": 4},
        "comment": {
            "zh": "天上同时有太阳、飞机、热气球、划船的小姑娘和飞起来的人，云朵还有表情。整幅画在讲一个自己的世界，想象很足。\n"
                  "太阳有脸、云会笑、船在天上划，这些改动都有用，把「天空」变成了游乐场（变形、转化）。\n"
                  "蓝色底子上的红船、黄飞机、彩条气球很跳，色彩对比用得好。\n"
                  "下一步可以试试：让物体有大有小、有近有远，比如把热气球画得更大、更靠前，画面会更有层次。",
            "en": "A sun, a jet, a hot-air balloon, a girl rowing a boat and a flying figure all share one sky, and the clouds have faces. This is a world of your own, full of ideas.\n"
                  "The sun's face, the smiling clouds and the boat rowing through the air all do real work: they turn the sky into a playground (Deformation, Transformation).\n"
                  "The red boat, yellow jet and striped balloon stand out sharply against the blue. Good use of contrast.\n"
                  "Next time, try making things different sizes: a bigger balloon in front, smaller things further back, so the picture has depth.",
        },
    },
    {
        "key": "line_low",
        "scores": {"line_combination": 2, "line_texture": 2},
        "title": {"zh": "线条两项偏低时", "en": "When both line dimensions are low"},
        "comment": {
            "zh": "轮廓都是一样粗细的一笔描出来的，头发和草地摸起来会是一样的。\n"
                  "下次画头发试试用很多短线排一排，画草地用尖尖的小线，线条会多出两种「手感」。",
            "en": "Every outline is one even stroke, so hair and grass would feel the same to touch.\n"
                  "Next time, try many short strokes side by side for hair and little spiky lines for grass. That gives your lines two new textures.",
        },
    },
    {
        "key": "org_mid",
        "scores": {"picture_organization": 3, "color_richness": 4},
        "title": {"zh": "构图 3、色彩 4 时", "en": "Organization 3, color 4"},
        "comment": {
            "zh": "颜色用了七八种，暖色的房子和冷色的夜空搭得好看。\n"
                  "东西都挤在左半边，右边空着。试试把月亮挪到右上角，或者让路一直伸到右边去。",
            "en": "You used seven or eight colors, and the warm house against the cool night sky looks great.\n"
                  "Everything sits in the left half and the right side is empty. Try moving the moon to the top right, or let the road run all the way across.",
        },
    },
    {
        "key": "realism_low_fine",
        "scores": {"realism": 1, "imagination": 5, "deformation": 4},
        "title": {"zh": "写实 1 不是坏事", "en": "Realism 1 is not a bad thing"},
        "comment": {
            "zh": "猫有六条腿、房子长着翅膀，这是你故意的，画面因此有了故事（想象、变形）。写实这一项分低只是说明「不像真的」，不用改。\n"
                  "可以试试给翅膀画上一根根羽毛，让它更像会飞。",
            "en": "The cat has six legs and the house has wings, and you meant it. That is what gives the picture a story (Imagination, Deformation). A low Realism score only says it does not look real, and it does not need to.\n"
                  "You could try drawing the feathers on the wings one by one, so they look ready to fly.",
        },
    },
]


def rubric_payload() -> Dict[str, Any]:
    """老师端 `/teacher/rubric` 的响应体。"""
    return {
        "source": SOURCE, "categories": CATEGORIES, "procedure": PROCEDURE,
        "dimensions": {k: {"criterion": v["criterion"],
                           "levels": [{"score": s, **v["levels"][s]} for s in (5, 4, 3, 2, 1)],
                           "reference": REFERENCE_DISTRIBUTION[k]} for k, v in RUBRIC.items()},
        "examples": EXAMPLES,
    }
