# -*- coding: utf-8 -*-
"""来源记录：内容来源（课标 / 测评框架 / 范式 / 量表）与构建规则来源（方法文献）分开。

每条片段（excerpt）保留：资料身份、原始定位（正文页与 PDF 页**分开**）、原文、原始要求、适用范围。
`verified` 记的是这段文字是怎么核对的——这份课标 PDF 是扫描件没有文字层，片段是 2026-10-11 按页图
人工转录的；拿不到原文的来源（PISA 两份、TCT-DP、TTCT）片段留空、状态 `待录入`，**不按记忆补写**。
摘要只是检索用；后面检查设计依据时读的是 `text`。
"""
from typing import Any, Dict, List

CONTENT, METHOD = "content", "method"

SOURCES: Dict[str, Dict[str, Any]] = {
    "kb2022": dict(
        kind=CONTENT, name="义务教育艺术课程标准（2022年版）", org="中华人民共和国教育部",
        version="2022年版", url="https://www.esph.com.cn/docs/2025-10/118486542f3f43459711ab9bb0c6c1a4.pdf",
        file_note="教育科学出版社网站托管的 PDF，131 页扫描件，无文字层",
        locator_note="正文页码 = PDF 页序 − 7（正文第 56 页 = PDF 第 63 页；2026-10-11 按页图核对）",
        role="教育范围：各学段接触哪些活动、学什么；不规定数字任务的对象数量、画布布局或提交形式",
        scope="义务教育 1–9 年级，美术部分按第一（1–2）、第二（3–5）、第三（6–7）、第四（8–9）学段各设 5 项学习任务"),
    "kidsartbench": dict(
        kind=CONTENT, name="KidsArtBench: Multi-Dimensional Children's Art Evaluation with Attribute-Aware MLLMs",
        org="KCL / ECNU / Sheffield", version="EACL 2026", url="https://aclanthology.org/2026.eacl-long.267/",
        file_note="本机 ~/下载/KidsArtBench.pdf，有文字层，2026-10-11 用 pdftotext 核对",
        role="作品评价量表来源（九维、1,046 幅、12 位专家）——**评作品，不评任务**",
        scope="儿童作品（5–15 岁）的多维评价"),
    "pisa2022-ct-framework": dict(
        kind=CONTENT, name="PISA 2022 Assessment and Analytical Framework — Chapter 4 Creative Thinking",
        org="OECD", version="2023 年出版（测评 2022）",
        url="https://www.oecd.org/content/dam/oecd/en/publications/reports/2023/08/pisa-2022-assessment-and-analytical-framework_a124aec8/dfe0bf9c-en.pdf",
        file_note="官方完整 PDF 292 页，有文字层；用户 2026-10-11 定位页码，本机下载后 pdftotext 核对。正文页 = PDF 页序 − 2",
        role="活动结构：产生多样构想 / 产生创意构想 / 评价与改进，是不同操作与产出；视觉表达面向 15 岁、用素材组合工具而非自由手绘",
        scope="15 岁学生；迁移到本项目只借活动形式，不沿用分数解释"),
    "pisa2022-vol3": dict(
        kind=CONTENT, name="PISA 2022 Results (Volume III): Creative Minds, Creative Schools — 样题 DT200Q02",
        org="OECD", version="2024",
        url="https://www.oecd.org/en/publications/pisa-2022-results-volume-iii_765ee8c2-en/full-report/component-25.html",
        file_note="附录 C「Science Fair Poster」单元第 2 题；官方原图 https://www.oecd.org/adobe/dynamicmedia/deliver/dm-aid--52441f23-7e5b-4d32-9d3a-0b23822bd8e3/image7.jpg "
                  "（用户与本机 2026-10-11 都看过图）。整本 PDF 的印刷页码没核，不补猜",
        role="「在已有视觉方案上进行改进」的形式来源", scope="同上"),
    "urban2005": dict(
        kind=CONTENT, name="Urban, K. K. (2005). Assessing creativity: The Test for Creative Thinking – Drawing Production (TCT-DP). International Education Journal, 6(2), 272–280",
        org="Urban（作者本人）", version="2005", url="https://files.eric.ed.gov/fulltext/EJ854980.pdf",
        file_note="作者论文，不是手册原页；ERIC PDF 有文字层，用户定位、本机 2026-10-11 pdftotext 核对。正文页 = PDF 页序 + 271",
        role="图形片段续画范式的一手依据（M3 的做法来源）。**不能据此说 M3 是原测验的平行题或已验证等值**；刺激与题面是本项目自制",
        scope="5 岁以上；纸笔；本项目改为数字画布上的矢量碎片"),
    "ttct": dict(
        kind=CONTENT, name="TTCT Interpretive Manual (2018)", org="Scholastic Testing Service",
        version="2018", url="https://www.ststesting.com/gift/TTCT_InterpMOD.2018.pdf",
        file_note="官方解释性手册；用户定位第 4 页，本机 2026-10-11 pdftotext 核对",
        role="**辅助来源**：第 4 页第 5 项是评价说明里的「不完整图形的综合」，不是图形版「图片补全」活动的施测指令，不拿它冒充题面原文",
        scope="同上"),
    # ---- 构建规则来源（方法）：解释「怎样把资料转成可检查的任务」，不能替代美术内容依据 ----
    "ecd": dict(kind=METHOD, name="A Brief Introduction to Evidence-Centered Design", org="Mislevy, Almond & Lukas (ETS)",
                version="2003", url="https://files.eric.ed.gov/fulltext/ED483399.pdf", file_note="未录入原文",
                role="任务模型：呈现材料、学生产出、任务特征；任务家族控制差异但不保证实例心理测量等值"),
    "decisive": dict(kind=METHOD, name="DECISIVE", org="ACL 2026", version="", url="https://aclanthology.org/2026.acl-long.1465/",
                     file_note="未录入原文", role="候选属性与用户偏好分离；数值化候选评分矩阵**不移用**"),
    "ace": dict(kind=METHOD, name="ACE（生成 / 反思 / 整理分工，增量更新上下文）", org="ICLR 2026", version="",
                url="https://proceedings.iclr.cc/paper_files/paper/2026/hash/8a94ff6f922d995d7d3f4ebf4143e442-Abstract-Conference.html",
                file_note="未录入原文", role="局部修订与经验条目化；不把模型自我评价当最终真值"),
    "browsergym": dict(kind=METHOD, name="BrowserGym", org="ServiceNow Research / TMLR 2025", version="",
                       url="https://www.servicenow.com/research/publication/thibault-le-sellier-de-chezelles-the-tmlr2025.html",
                       file_note="未录入原文", role="任务初始状态设置与结果验证分开 → 「材料应是什么」与「实际材料是否满足」分开"),
    "workarena++": dict(kind=METHOD, name="WorkArena++", org="arXiv 2407.05291", version="", url="https://arxiv.org/html/2407.05291v1",
                        file_note="未录入原文", role="按操作与技能组织任务，同一任务内实例化不同配置（变式的组织方式）"),
    "dsg": dict(kind=METHOD, name="Davidsonian Scene Graph", org="ICLR 2024 / arXiv 2310.18235", version="",
                url="https://arxiv.org/html/2310.18235", file_note="未录入原文",
                role="把图像要求拆成对象 / 属性 / 关系并建立依赖；用于研究者提供的刺激材料，不用于评学生作品；不采用其平均分"),
    "alce": dict(kind=METHOD, name="ALCE（Enabling LLMs to Generate Text with Citations）", org="EMNLP 2023", version="",
                 url="https://aclanthology.org/2023.emnlp-main.398/", file_note="未录入原文",
                 role="内容正确性与引用质量分开评：附有引用 ≠ 引用真正支持该内容"),
}

VERIFIED_PAGE_IMAGE = "页图人工转录 2026-10-11；2026-10-12 逐条按页图复核（docs/来源核查_2026-10-12.md）"
PENDING = "待录入"


def _kb(eid: str, body_page: int, band: str, heading: str, text: str, requirement: str,
        scope: str = "") -> Dict[str, Any]:
    return dict(id=eid, source="kb2022", page_body=body_page, page_pdf=body_page + 7, band=band,
                heading=heading, text=text, requirement=requirement, scope=scope or f"课标第{band}学段美术",
                verified=VERIFIED_PAGE_IMAGE)


EXCERPTS: Dict[str, Dict[str, Any]] = {e["id"]: e for e in [
    _kb("kb:p49:overview", 49, "总", "五、课程内容（美术）总说",
        "每一学段均设置5项学习任务，将美术语言（造型元素和形式原理）贯穿其中。5项学习任务既各有侧重，又相互联系。"
        "每一学段均以注重发展学生审美感知和文化理解素养的“欣赏·评述”为起点，到以强调发展学生艺术表现和创意实践素养的"
        "“造型·表现”和“设计·应用”，再到加强课程内容、社会生活与学生经验之间联系的“综合·探索”。义务教育阶段共设置20项学习任务。",
        "学段结构：每学段 5 项任务；这是分层起点，不是已校准的难度分级", "义务教育全学段"),
    _kb("kb:p3:stages", 3, "总", "三、设计思路 1. 适应学生发展，分段设计课程",
        "第一阶段（1～2年级）以艺术综合为主，体现从幼儿园综合活动到小学分科课程的过渡与衔接；第二阶段（3～7年级）以音乐和美术为主，"
        "有机融入姊妹艺术，为学生掌握较为全面的艺术基础知识和基本技能奠定基础；第三阶段（8～9年级）开设艺术选项，帮助学生掌握1～2项艺术特长，与高中模块化教学相衔接。",
        "本项目「小学版 / 初中版」两个版本大致对应 3–7 年级（美术为主）与 8–9 年级（选项）", "义务教育全学段"),
    _kb("kb:p49:t1-signs", 49, "一", "学习任务1：欣赏身边的美 · 内容要求",
        "识别学校或社区公共场所中常见的标识，从线条、形状、色彩的角度进行分析，了解其用途和所传递的信息。",
        "认识标识的用途与信息（欣赏，不是设计）"),
    _kb("kb:p49:t1-nature", 49, "一", "学习任务1：欣赏身边的美 · 内容要求",
        "观赏周边自然环境中的山水、树木、花草、动物等，感知其形状美、色彩美和肌理美，体会美存在于我们周围的环境之中。",
        "观察自然对象的形状 / 色彩 / 肌理"),
    _kb("kb:p50:t2-intro", 50, "一", "学习任务2：表达自己的感受 · 导语",
        "本学习任务主要引导学生尝试使用不同的工具、材料和媒介，以及线条、形状、色彩、肌理等造型元素和对称、重复等形式原理，"
        "按照自己的想法，以平面、立体或动态等形式表达所见所闻、所感所想。",
        "用造型元素按自己的想法表达所见所闻所感所想（个人表达）"),
    _kb("kb:p50:t2-req", 50, "一", "学习任务2：表达自己的感受 · 学业要求",
        "对美术创作具有好奇心和想象力。能使用不同的工具、材料和媒介，创作不同形式的美术作品，表达自己的感受。",
        "好奇心与想象力；用不同媒介创作并表达感受"),
    _kb("kb:p51:t3-intro", 51, "一", "学习任务3：改进生活用品 · 导语",
        "本学习任务主要引导学生学会从外观和使用功能等方面了解物品的特点，针对某件物品提出自己的改进意见，进行装饰和美化，初步形成设计意识。",
        "从外观与功能了解物品 → 提出改进 → 装饰美化（有目的的设计 / 改进已有物）"),
    _kb("kb:p51:t3-req", 51, "一", "学习任务3：改进生活用品 · 内容要求",
        "针对自己或他人的一件生活用品，根据外形和使用功能等，提出改进意见，进行装饰和美化。",
        "对一件生活用品提出改进意见"),
    _kb("kb:p52:t5-design", 52, "一", "学习任务5：参与造型游戏活动 · 内容要求",
        "利用画笔或计算机，运用线条、形状、色彩等造型元素，以及对称、重复等形式原理，为自己设计名片，为参加小组或班级活动的同学设计席卡等。",
        "用画笔或计算机做有明确用途的小设计（名片、席卡）"),
    _kb("kb:p53:t2-teach", 53, "一", "教学提示 · “表达自己的感受”的教学",
        "“表达自己的感受”的教学，应采用启发和创作相结合的教学方式，指导学生使用不同的工具、材料和媒介，创作不同表现形式的美术作品，"
        "表达自己的想法；注重引导学生理解“美术学习始终要保持好奇心和想象力”。",
        "启发 + 创作；保持好奇心和想象力"),
    _kb("kb:p54:t2-intro", 54, "二", "学习任务2：表达自己的想法 · 导语",
        "本学习任务主要引导学生探索用传统与现代的工具、材料和媒介，创作平面、立体或动态等表现形式的美术作品，表现自己的所见所闻、所感所想，"
        "学会以视觉形象的方式与他人交流。",
        "用现代媒介（含数字）创作平面作品，以视觉形象与人交流"),
    _kb("kb:p54:t2-color", 54, "二", "学习任务2：表达自己的想法 · 内容要求",
        "通过调和不同的颜色，认识原色、间色、复色、对比色和邻近色的特点。",
        "色彩知识：原色 / 间色 / 复色 / 对比色 / 邻近色"),
    _kb("kb:p55:t2-perspective", 55, "二", "学习任务2：表达自己的想法 · 内容要求",
        "观察室内或室外物体在空间中“近大远小”的变化规律，了解平行透视的知识。",
        "观察空间中物体的近大远小（观察与表现：空间关系）"),
    _kb("kb:p55:t2-methods", 55, "二", "学习任务2：表达自己的想法 · 内容要求",
        "根据自己对生活的感受与想法，使用不同的工具、材料和媒介，采用写实、夸张等手法进行表现。",
        "写实、夸张两种表现手法"),
    _kb("kb:p55:t2-req", 55, "二", "学习任务2：表达自己的想法 · 学业要求",
        "能使用传统或现代的工具、材料和媒介，创作不同表现形式的美术作品，表达自己对生活的看法。"
        "在创作美术作品时，能提出各种构想，并尝试运用各种表现形式和方法，创作富有创意的美术作品。",
        "提出各种构想（多样化构想在课标里的位置）并创作富有创意的作品"),
    _kb("kb:p55:t3-intro", 55, "二", "学习任务3：装点我们的生活 · 导语",
        "本学习任务主要引导学生了解“实用与美观相结合”的设计原则，为班级、学校的活动设计物品，体会设计能改善和美化我们的生活。",
        "为班级、学校活动做设计（校园情境的有目的的设计）"),
    _kb("kb:p55:t3-improve", 55, "二", "学习任务3：装点我们的生活 · 内容要求（这句跨 p55–56，「设计原｜则」处分页）",
        "观察学习与生活用品，了解“实用与美观相结合”的设计原则，从舒适、美观和便利的角度，发现其不足之处，用手绘草图等形式呈现自己的改进想法。",
        "发现不足 → 用手绘草图呈现改进想法（评价与改进）"),
    _kb("kb:p56:t3-visual-design", 56, "二", "学习任务3：装点我们的生活 · 内容要求",
        "利用画笔或计算机，运用造型元素和形式原理，为班级或学校的活动设计标识、请柬、贺卡、图表、海报等。",
        "用画笔或计算机为班级 / 学校活动设计标识、请柬、贺卡、图表、海报"),
    _kb("kb:p56:t3-req", 56, "二", "学习任务3：装点我们的生活 · 学业要求",
        "能针对学习或生活用品设计中存在的不足之处，用手绘草图的形式提出改进建议。能从实用、美观和环保的角度，为班级、学校的活动设计各种作品。",
        "改进建议（草图）；为班级学校活动设计作品"),
    _kb("kb:p58:t2-teach", 58, "二", "教学提示 · “表达自己的想法”的教学重点",
        "“表达自己的想法”的教学重点是：引导学生观察生活，收集素材，提炼主题，进行创造性表达；在学生产生各种构想时，及时给予鼓励与指导，"
        "帮助学生提炼主题，指导学生采用平面、立体或动态等表现形式，创作富有创意的美术作品，表达自己对生活的感受与想法；"
        "注重引导学生理解“美术是认识与表现自我和他人的重要方式”。",
        "观察生活 → 提炼主题 → 创造性表达；产生各种构想时给予鼓励"),
    _kb("kb:p58:copy-vs-change", 58, "二", "教学提示",
        "在美术活动中，教师要让学生知道以临摹、添加、拼贴等手法模仿和改变原作与抄袭作品之间的区别。",
        "临摹、添加、拼贴是被承认的「模仿与改变原作」手法（支持照着参考图画、在已有画面上添加）"),
    _kb("kb:p58:contexts", 59, "二", "教学提示 · 情境素材建议（起句在 p58 末，举例在 p59 首；2026-10-12 按页图核对）",
        "……发掘与学生生活经验相关或学生感兴趣的素材，如“诗情画意”“我是能工巧匠”“中国年”“本草的故事”“难忘的红色之旅”“以编程改进物品与居室环境”等。",
        "情境素材是建议性的举例，不是规定题材"),
    _kb("kb:p60:t2-intro", 60, "三", "学习任务2：传递我们的创意 · 导语",
        "本学习任务主要引导学生运用传统与现代的工具、材料和媒介，以及所习得的美术知识、技能和思维方式，创作平面、立体或动态等表现形式的美术作品，提升创意表达能力。",
        "创意表达（6–7 年级个人表达的主任务）"),
    _kb("kb:p60:t2-color", 60, "三", "学习任务2：传递我们的创意 · 内容要求",
        "学习冷色调、暖色调、互补色、对比色等方面的色彩知识，体验不同色彩所带来的不同感受。",
        "冷暖 / 互补 / 对比；**色彩带来不同感受**（M6 的直接依据）"),
    _kb("kb:p60:t2-composition", 60, "三", "学习任务2：传递我们的创意 · 内容要求",
        "分析圆形、S形、三角形等构图形式的美术作品，体会不同构图形式的美感。",
        "构图形式（画面组织的内容属性）"),
    _kb("kb:p60:t2-perspective", 60, "三", "学习任务2：传递我们的创意 · 内容要求",
        "从不同角度观察立方体物品，了解平行透视与成角透视的区别。",
        "观察立体物品的透视（观察与表现：空间关系）"),
    _kb("kb:p60:t2-methods", 60, "三", "学习任务2：传递我们的创意 · 内容要求",
        "使用不同的工具、材料和媒介，采用写实、夸张、变形等手法，表现自己对生活的感受和认识。",
        "写实、夸张、变形三种手法（变形 = Deformation 的课程位置）"),
    _kb("kb:p61:t2-req", 61, "三", "学习任务2：传递我们的创意 · 学业要求",
        "6年级：能使用传统与现代的工具、材料和媒介，采用写实、夸张等手法，创作美术作品。能提出各种构想，尝试用多种表现形式和方法创作美术作品。"
        "7年级：能使用传统与现代的工具、材料和媒介，采用写实、夸张、变形等手法，创作美术作品。能提出各种构想，并灵活变通，用各种表现形式和方法创作有创意的美术作品。",
        "6 年级与 7 年级分开写的学业要求；「提出各种构想」两年级都有"),
    _kb("kb:p61:t3-intro", 61, "三", "学习任务3：营造环境 · 导语",
        "本学习任务主要引导学生根据“人与自然和谐共生”的设计原则，对学校或社区进行环境规划，增强社会责任意识。",
        "环境设计 / 规划（有目的的设计，6–7 年级）"),
    _kb("kb:p62:t3-improve", 62, "三", "学习任务3：营造环境 · 内容要求",
        "根据调研中发现的问题，提出改进建议，用手绘或计算机制作等方式绘制草图，利用废弃物品制作模型，进行展示与交流。"
        "根据不同活动的需要设计海报、请柬、封面、书籍装帧或统计图表等。",
        "发现问题 → 改进建议 → 草图（评价与改进）；为活动设计海报等"),
    _kb("kb:p65:t2-teach", 65, "三", "教学提示 · “传递我们的创意”的教学重点",
        "“传递我们的创意”的教学重点是：引导学生学习美术家的思维方式和表现方法；在学生产生各种构想时，及时给予鼓励和指导，以讲授、演示、练习、探究、合作学习等教学方式，"
        "帮助学生提高感悟能力、提炼主题的能力，以及运用平面、立体或动态等表现形式表达对生活的认识和思考的能力，创作富有创意的美术作品。",
        "产生各种构想时给予鼓励与指导"),
    _kb("kb:p66:contexts", 66, "三", "教学提示 · 情境素材建议",
        "……发掘与学生生活经验相关或学生感兴趣的素材，如“世界美术之旅”“中国画的魅力”“科学幻想”“校园美术馆”“点亮乡村计划”“校园中的故事”等。",
        "「科学幻想」「校园中的故事」是课标列出的情境素材举例（建议，不是规定）"),
    _kb("kb:p68:t2-intro", 68, "四", "学习任务2：表现无限创意 · 导语",
        "本学习任务主要引导学生运用传统与现代的工具、材料和媒介，创作平面、立体或动态等表现形式的美术作品，创造性地表达对自然与社会的感受、思考和认识，发展创造性思维能力。",
        "创造性表达（8–9 年级）"),
    _kb("kb:p68:t2-color", 68, "四", "学习任务2：表现无限创意 · 内容要求",
        "学习有关色彩三要素、色彩情感特征等方面的知识。",
        "色彩情感特征"),
    _kb("kb:p68:t2-methods", 68, "四", "学习任务2：表现无限创意 · 内容要求",
        "根据自己对生活的感受与认识，使用不同的工具、材料和媒介，采用写实、夸张、变形、抽象等手法创作美术作品。",
        "写实、夸张、变形、抽象四种手法（抽象 = M7 第一步的课程位置）"),
    _kb("kb:p68:t2-req", 68, "四", "学习任务2：表现无限创意 · 学业要求",
        "在创作美术作品时，能通过想象、联想、归类、重组等方式进行构思和实践，创作富有创意的美术作品。",
        "想象、联想、归类、重组（M5 融合 / M8 规则世界的构思方式）"),
    dict(id="kab:table1", source="kidsartbench", page_body=None, page_pdf=3, band="", heading="Table 1: KidsArtBench rubric dimensions",
         text="Realism — Accuracy in depicting subjects and objects; Deformation — Creative reinterpretation of reality; Imagination — Novelty and originality of concepts; "
              "Color Richness — Diversity and harmony of color palette; Color Contrast — Visual impact through hue interactions; Line Combination — Structural arrangement of strokes; "
              "Line Texture — Expressive tactile quality of linework; Picture Organization — Balanced composition and spatial logic; Transformation — Effective rendering of abstract concepts.",
         requirement="九个作品评价维度的定义（作品，不是任务）", scope="儿童作品 5–15 岁",
         verified="pdftotext 核对 2026-10-11"),
    dict(id="kab:dataset", source="kidsartbench", page_body=None, page_pdf=2, band="", heading="3 Dataset",
         text="We collected 1,046 original artworks from students aged 5–15 … Each artwork was independently scored by at least two trained art educators across nine standardized rubric dimensions.",
         requirement="量表的标定对象是作品，专家至少两人独立打分", scope="", verified="pdftotext 核对 2026-10-11"),
    dict(id="pisa:processes", source="pisa2022-ct-framework", page_body=150, page_pdf=152, band="", heading="Chapter 4 · 创造性思维能力模型（图 4.2 上方）",
         text="…decomposed into three distinct facets for measurement purposes in the PISA 2022 test. These three facets are: 1) generate diverse ideas; 2) generate creative ideas; and 3) evaluate and improve ideas.",
         requirement="产生多样构想 / 产生创意构想 / 评价与改进是三种不同的过程，各自有不同的操作与产出（具体定义在正文 151 页 / PDF 153 页三个小节）",
         scope="15 岁", verified="用户定位 + 本机 pdftotext 核对 2026-10-11"),
    dict(id="pisa:age", source="pisa2022-ct-framework", page_body=149, page_pdf=151, band="", heading="Objective and focus of the PISA 2022 Creative Thinking assessment",
         text="The PISA 2022 assessment focuses on the creative thinking processes that can be reasonably demonstrated by 15-year-old students.",
         requirement="原测评面向 15 岁；迁移到本项目年龄只借活动形式，不沿用分数解释", scope="15 岁", verified="用户定位 + 本机 pdftotext 核对 2026-10-11"),
    dict(id="pisa:visual-tool", source="pisa2022-ct-framework", page_body=153, page_pdf=155, band="", heading="Visual expression domain — the drawing tool（页首续段）",
         text="…not enable free drawing, but students can create visual compositions by dragging and dropping elements…",
         requirement="视觉表达用素材组合式的设计工具（拖放、缩放、旋转、改色），不是自由手绘；本项目改成自由绘画是研究性改编",
         scope="15 岁", verified="用户定位 + 本机 pdftotext 核对 2026-10-11"),
    dict(id="pisa:dt200q02", source="pisa2022-vol3", page_body=None, page_pdf=None, band="", heading="Annex C · Science Fair Poster · Question 2/2 (DT200Q02)",
         text="Improve the poster on the right to make it relevant to the theme of ‘Life in Deep Space.’ Your improvements should be original in the sense that not many people would think of changing the poster in this way. Make sure that the existing poster design is still visible in the final design. Describe your design in one sentence in the box below. We recommend that you spend no longer than 5 minutes on this question.",
         requirement="「在已有视觉方案上改进」的题型：改进要有原创性、原设计仍可见、一句话描述、建议 5 分钟；官方归为视觉表达领域的「评价与改进」",
         scope="15 岁；贴纸式工具", verified="官方题面图，用户与本机 2026-10-11 都看过；整本 PDF 页码未核"),
    dict(id="urban2005:paradigm", source="urban2005", page_body=273, page_pdf=2, band="", heading="Design and Construction",
         text="The test asks the testee to complete a drawing on the basis of some given figural fragments.",
         requirement="以给定的图形片段为基础完成一幅画；片段刻意做成不完整、不规则以求最大灵活性", scope="5 岁以上",
         verified="用户定位 + 本机 pdftotext 核对 2026-10-11"),
    dict(id="ttct:synthesis", source="ttct", page_body=4, page_pdf=4, band="", heading="Interpretive Manual · 5. Synthesis of Incomplete Figures",
         text="5. Synthesis of Incomplete Figures—the combination of two or more figures is quite rare and points out an…",
         requirement="辅助来源：评价说明里提到把不完整图形组合起来的表现；不是施测指令", scope="",
         verified="用户定位 + 本机 pdftotext 核对 2026-10-11"),
]}

# 来源关系（设计从哪来）——和检查结果分开的那套标签
VERBATIM, ADAPTED, PROJECT = "原文明确规定", "基于来源改编", "项目新增条件"
RELATIONS = (VERBATIM, ADAPTED, PROJECT)


def excerpt(eid: str) -> Dict[str, Any]:
    return EXCERPTS[eid]


def excerpts_for(source_id: str) -> List[Dict[str, Any]]:
    return [e for e in EXCERPTS.values() if e["source"] == source_id]
