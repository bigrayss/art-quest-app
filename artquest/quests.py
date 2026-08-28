"""Stage 1 Creative Quests — 5 open-ended tasks, no copy-this-template answers.

Each quest names the KidsArtBench dimensions it mainly activates (focus_dims)
so scoring and feedback can emphasise them (guide §02/§03).
"""

QUESTS = [
    {
        "id": "emotion_alone",
        "type": "情绪表达",
        "title": "画出「孤独」或「快乐」",
        "prompt": "不要直接画一张脸或表情。用颜色、空间、物体和构图，让整张画面本身传达「孤独」或「快乐」中的一种感觉。",
        "hint": "想一想：这种感觉是大的还是小的？是空旷的还是拥挤的？是冷的还是暖的？",
        "focus_dims": ["color_contrast", "picture_organization", "imagination"],
    },
    {
        "id": "imagine_animal",
        "type": "想象",
        "title": "设计一种不存在的动物",
        "prompt": "创造一种世界上没有的动物。它住在哪里？吃什么？有什么特别的本领？把它和它生活的地方画出来。",
        "hint": "可以把两三种你熟悉的动物或物体的特点组合起来，再改变大小和比例。",
        "focus_dims": ["imagination", "deformation", "transformation"],
    },
    {
        "id": "transform_chair",
        "type": "Transformation",
        "title": "一把椅子变成了……",
        "prompt": "从一把普通的椅子出发，把它变成一个完全不同用途的东西——交通工具、生物、建筑、乐器，都可以。让人还能认出它曾经是一把椅子。",
        "hint": "先想它的哪一部分保留，哪一部分改变，再决定它的新功能。",
        "focus_dims": ["transformation", "imagination", "line_combination"],
    },
    {
        "id": "color_rain_city",
        "type": "Color / Composition",
        "title": "只用三种颜色画下雨的城市",
        "prompt": "选择三种颜色（黑白不算），只用这三种颜色画一座下雨的城市。想办法让画面有远近、有明暗、有雨的感觉。",
        "hint": "同一种颜色可以画得深一点或淡一点，也可以叠加。",
        "focus_dims": ["color_richness", "color_contrast", "picture_organization"],
    },
    {
        "id": "story_character_home",
        "type": "Story",
        "title": "我的角色和它的家",
        "prompt": "创造一个属于你的角色，并画出它的家。家里应该能看出这个角色喜欢什么、害怕什么、每天在做什么。",
        "hint": "角色可以很小，家可以很大；或者相反。让物品替角色讲故事。",
        "focus_dims": ["picture_organization", "line_combination", "imagination"],
    },
]

QUESTS_BY_ID = {q["id"]: q for q in QUESTS}

EMOTIONS = ["开心", "平静", "兴奋", "紧张", "难过", "无聊", "好奇", "说不清"]
