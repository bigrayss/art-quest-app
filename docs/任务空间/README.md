# 任务空间（Phase 0 任务初始化）· 任务库 v2.7

> 由 `tools/taskspace_report.py` 生成，**别手改**；改 `artquest/taskspace/*.py` 再重跑。

候选 110 道：clear 110 · open 0 · blocked 0。

现有产品能力（任务要求的操作必须由工具 + 材料共同支持）：

| 能力 | 有没有 |
| --- | --- |
| single_canvas_drawing | 有 |
| reference_always_visible | 有 |
| reference_on_demand | 有 |
| vector_stimulus_on_canvas | 有 |
| colour_palette_everywhere | 有 |
| two_phase_metadata | 有 |
| multi_sketch_output | **没有** |
| movable_objects | **没有** |
| editable_starting_artwork | **没有** |
| text_input | **没有** |
| timer | **没有** |

## 1. 来源

内容来源解释「为什么设计这种美术活动」，方法来源解释「怎样把资料转成可检查的任务」；两套记录不混写。

| id | 资料 | 类 | 作用 | 已录入片段 | 文件说明 |
| --- | --- | --- | --- | --- | --- |
| kb2022 | 义务教育艺术课程标准（2022年版） | 内容 | 教育范围：各学段接触哪些活动、学什么；不规定数字任务的对象数量、画布布局或提交形式 | 36/36 | 教育科学出版社网站托管的 PDF，131 页扫描件，无文字层 |
| kidsartbench | KidsArtBench: Multi-Dimensional Children's Art Evaluation with Attribute-Aware MLLMs | 内容 | 作品评价量表来源（九维、1,046 幅、12 位专家）——**评作品，不评任务** | 2/2 | 本机 ~/下载/KidsArtBench.pdf，有文字层，2026-10-11 用 pdftotext 核对 |
| pisa2022-ct-framework | PISA 2022 Assessment and Analytical Framework — Chapter 4 Creative Thinking | 内容 | 活动结构：产生多样构想 / 产生创意构想 / 评价与改进，是不同操作与产出；视觉表达面向 15 岁、用素材组合工具而非自由手绘 | 3/3 | 官方完整 PDF 292 页，有文字层；用户 2026-10-11 定位页码，本机下载后 pdftotext 核对。正文页 = PDF 页序 − 2 |
| pisa2022-vol3 | PISA 2022 Results (Volume III): Creative Minds, Creative Schools — 样题 DT200Q02 | 内容 | 「在已有视觉方案上进行改进」的形式来源 | 1/1 | 附录 C「Science Fair Poster」单元第 2 题；官方原图 https://www.oecd.org/adobe/dynamicmedia/deliver/dm-aid--52441f23-7e5b-4d32-9d3a-0b23822bd8e3/image7.jpg （用户与本机 2026-10-11 都看过图）。整本 PDF 的印刷页码没核，不补猜 |
| urban2005 | Urban, K. K. (2005). Assessing creativity: The Test for Creative Thinking – Drawing Production (TCT-DP). International Education Journal, 6(2), 272–280 | 内容 | 图形片段续画范式的一手依据（M3 的做法来源）。**不能据此说 M3 是原测验的平行题或已验证等值**；刺激与题面是本项目自制 | 1/1 | 作者论文，不是手册原页；ERIC PDF 有文字层，用户定位、本机 2026-10-11 pdftotext 核对。正文页 = PDF 页序 + 271 |
| ttct | TTCT Interpretive Manual (2018) | 内容 | **辅助来源**：第 4 页第 5 项是评价说明里的「不完整图形的综合」，不是图形版「图片补全」活动的施测指令，不拿它冒充题面原文 | 1/1 | 官方解释性手册；用户定位第 4 页，本机 2026-10-11 pdftotext 核对 |
| ecd | A Brief Introduction to Evidence-Centered Design | 方法 | 任务模型：呈现材料、学生产出、任务特征；任务家族控制差异但不保证实例心理测量等值 | 0/0 | 未录入原文 |
| decisive | DECISIVE | 方法 | 候选属性与用户偏好分离；数值化候选评分矩阵**不移用** | 0/0 | 未录入原文 |
| ace | ACE（生成 / 反思 / 整理分工，增量更新上下文） | 方法 | 局部修订与经验条目化；不把模型自我评价当最终真值 | 0/0 | 未录入原文 |
| browsergym | BrowserGym | 方法 | 任务初始状态设置与结果验证分开 → 「材料应是什么」与「实际材料是否满足」分开 | 0/0 | 未录入原文 |
| workarena++ | WorkArena++ | 方法 | 按操作与技能组织任务，同一任务内实例化不同配置（变式的组织方式） | 0/0 | 未录入原文 |
| dsg | Davidsonian Scene Graph | 方法 | 把图像要求拆成对象 / 属性 / 关系并建立依赖；用于研究者提供的刺激材料，不用于评学生作品；不采用其平均分 | 0/0 | 未录入原文 |
| alce | ALCE（Enabling LLMs to Generate Text with Citations） | 方法 | 内容正确性与引用质量分开评：附有引用 ≠ 引用真正支持该内容 | 0/0 | 未录入原文 |

### 1.1 片段（正文页与 PDF 页分开记；`待录入` = 没拿到原文，不按记忆补）

| 片段 id | 学段 | 位置 | 正文页 | PDF 页 | 核对 | 原始要求 |
| --- | --- | --- | --- | --- | --- | --- |
| kb:p49:overview | 总 | 五、课程内容（美术）总说 | 49 | 56 | 页图人工转录 2026-10-11 | 学段结构：每学段 5 项任务；这是分层起点，不是已校准的难度分级 |
| kb:p3:stages | 总 | 三、设计思路 1. 适应学生发展，分段设计课程 | 3 | 10 | 页图人工转录 2026-10-11 | 本项目「小学版 / 初中版」两个版本大致对应 3–7 年级（美术为主）与 8–9 年级（选项） |
| kb:p49:t1-signs | 一 | 学习任务1：欣赏身边的美 · 内容要求 | 49 | 56 | 页图人工转录 2026-10-11 | 认识标识的用途与信息（欣赏，不是设计） |
| kb:p49:t1-nature | 一 | 学习任务1：欣赏身边的美 · 内容要求 | 49 | 56 | 页图人工转录 2026-10-11 | 观察自然对象的形状 / 色彩 / 肌理 |
| kb:p50:t2-intro | 一 | 学习任务2：表达自己的感受 · 导语 | 50 | 57 | 页图人工转录 2026-10-11 | 用造型元素按自己的想法表达所见所闻所感所想（个人表达） |
| kb:p50:t2-req | 一 | 学习任务2：表达自己的感受 · 学业要求 | 50 | 57 | 页图人工转录 2026-10-11 | 好奇心与想象力；用不同媒介创作并表达感受 |
| kb:p51:t3-intro | 一 | 学习任务3：改进生活用品 · 导语 | 51 | 58 | 页图人工转录 2026-10-11 | 从外观与功能了解物品 → 提出改进 → 装饰美化（有目的的设计 / 改进已有物） |
| kb:p51:t3-req | 一 | 学习任务3：改进生活用品 · 内容要求 | 51 | 58 | 页图人工转录 2026-10-11 | 对一件生活用品提出改进意见 |
| kb:p52:t5-design | 一 | 学习任务5：参与造型游戏活动 · 内容要求 | 52 | 59 | 页图人工转录 2026-10-11 | 用画笔或计算机做有明确用途的小设计（名片、席卡） |
| kb:p53:t2-teach | 一 | 教学提示 · “表达自己的感受”的教学 | 53 | 60 | 页图人工转录 2026-10-11 | 启发 + 创作；保持好奇心和想象力 |
| kb:p54:t2-intro | 二 | 学习任务2：表达自己的想法 · 导语 | 54 | 61 | 页图人工转录 2026-10-11 | 用现代媒介（含数字）创作平面作品，以视觉形象与人交流 |
| kb:p54:t2-color | 二 | 学习任务2：表达自己的想法 · 内容要求 | 54 | 61 | 页图人工转录 2026-10-11 | 色彩知识：原色 / 间色 / 复色 / 对比色 / 邻近色 |
| kb:p55:t2-perspective | 二 | 学习任务2：表达自己的想法 · 内容要求 | 55 | 62 | 页图人工转录 2026-10-11 | 观察空间中物体的近大远小（观察与表现：空间关系） |
| kb:p55:t2-methods | 二 | 学习任务2：表达自己的想法 · 内容要求 | 55 | 62 | 页图人工转录 2026-10-11 | 写实、夸张两种表现手法 |
| kb:p55:t2-req | 二 | 学习任务2：表达自己的想法 · 学业要求 | 55 | 62 | 页图人工转录 2026-10-11 | 提出各种构想（多样化构想在课标里的位置）并创作富有创意的作品 |
| kb:p55:t3-intro | 二 | 学习任务3：装点我们的生活 · 导语 | 55 | 62 | 页图人工转录 2026-10-11 | 为班级、学校活动做设计（校园情境的有目的的设计） |
| kb:p55:t3-improve | 二 | 学习任务3：装点我们的生活 · 内容要求 | 55 | 62 | 页图人工转录 2026-10-11 | 发现不足 → 用手绘草图呈现改进想法（评价与改进） |
| kb:p56:t3-visual-design | 二 | 学习任务3：装点我们的生活 · 内容要求 | 56 | 63 | 页图人工转录 2026-10-11 | 用画笔或计算机为班级 / 学校活动设计标识、请柬、贺卡、图表、海报 |
| kb:p56:t3-req | 二 | 学习任务3：装点我们的生活 · 学业要求 | 56 | 63 | 页图人工转录 2026-10-11 | 改进建议（草图）；为班级学校活动设计作品 |
| kb:p58:t2-teach | 二 | 教学提示 · “表达自己的想法”的教学重点 | 58 | 65 | 页图人工转录 2026-10-11 | 观察生活 → 提炼主题 → 创造性表达；产生各种构想时给予鼓励 |
| kb:p58:copy-vs-change | 二 | 教学提示 | 58 | 65 | 页图人工转录 2026-10-11 | 临摹、添加、拼贴是被承认的「模仿与改变原作」手法（支持照着参考图画、在已有画面上添加） |
| kb:p58:contexts | 二 | 教学提示 · 情境素材建议 | 58 | 65 | 页图人工转录 2026-10-11 | 情境素材是建议性的举例，不是规定题材 |
| kb:p60:t2-intro | 三 | 学习任务2：传递我们的创意 · 导语 | 60 | 67 | 页图人工转录 2026-10-11 | 创意表达（6–7 年级个人表达的主任务） |
| kb:p60:t2-color | 三 | 学习任务2：传递我们的创意 · 内容要求 | 60 | 67 | 页图人工转录 2026-10-11 | 冷暖 / 互补 / 对比；**色彩带来不同感受**（M6 的直接依据） |
| kb:p60:t2-composition | 三 | 学习任务2：传递我们的创意 · 内容要求 | 60 | 67 | 页图人工转录 2026-10-11 | 构图形式（画面组织的内容属性） |
| kb:p60:t2-perspective | 三 | 学习任务2：传递我们的创意 · 内容要求 | 60 | 67 | 页图人工转录 2026-10-11 | 观察立体物品的透视（观察与表现：空间关系） |
| kb:p60:t2-methods | 三 | 学习任务2：传递我们的创意 · 内容要求 | 60 | 67 | 页图人工转录 2026-10-11 | 写实、夸张、变形三种手法（变形 = Deformation 的课程位置） |
| kb:p61:t2-req | 三 | 学习任务2：传递我们的创意 · 学业要求 | 61 | 68 | 页图人工转录 2026-10-11 | 6 年级与 7 年级分开写的学业要求；「提出各种构想」两年级都有 |
| kb:p61:t3-intro | 三 | 学习任务3：营造环境 · 导语 | 61 | 68 | 页图人工转录 2026-10-11 | 环境设计 / 规划（有目的的设计，6–7 年级） |
| kb:p62:t3-improve | 三 | 学习任务3：营造环境 · 内容要求 | 62 | 69 | 页图人工转录 2026-10-11 | 发现问题 → 改进建议 → 草图（评价与改进）；为活动设计海报等 |
| kb:p65:t2-teach | 三 | 教学提示 · “传递我们的创意”的教学重点 | 65 | 72 | 页图人工转录 2026-10-11 | 产生各种构想时给予鼓励与指导 |
| kb:p66:contexts | 三 | 教学提示 · 情境素材建议 | 66 | 73 | 页图人工转录 2026-10-11 | 「科学幻想」「校园中的故事」是课标列出的情境素材举例（建议，不是规定） |
| kb:p68:t2-intro | 四 | 学习任务2：表现无限创意 · 导语 | 68 | 75 | 页图人工转录 2026-10-11 | 创造性表达（8–9 年级） |
| kb:p68:t2-color | 四 | 学习任务2：表现无限创意 · 内容要求 | 68 | 75 | 页图人工转录 2026-10-11 | 色彩情感特征 |
| kb:p68:t2-methods | 四 | 学习任务2：表现无限创意 · 内容要求 | 68 | 75 | 页图人工转录 2026-10-11 | 写实、夸张、变形、抽象四种手法（抽象 = M7 第一步的课程位置） |
| kb:p68:t2-req | 四 | 学习任务2：表现无限创意 · 学业要求 | 68 | 75 | 页图人工转录 2026-10-11 | 想象、联想、归类、重组（M5 融合 / M8 规则世界的构思方式） |
| kab:table1 |  | Table 1: KidsArtBench rubric dimensions | — | 3 | pdftotext 核对 2026-10-11 | 九个作品评价维度的定义（作品，不是任务） |
| kab:dataset |  | 3 Dataset | — | 2 | pdftotext 核对 2026-10-11 | 量表的标定对象是作品，专家至少两人独立打分 |
| pisa:processes |  | Chapter 4 · 创造性思维能力模型（图 4.2 上方） | 150 | 152 | 用户定位 + 本机 pdftotext 核对 2026-10-11 | 产生多样构想 / 产生创意构想 / 评价与改进是三种不同的过程，各自有不同的操作与产出（具体定义在正文 151 页 / PDF 153 页三个小节） |
| pisa:age |  | Objective and focus of the PISA 2022 Creative Thinking assessment | 149 | 151 | 用户定位 + 本机 pdftotext 核对 2026-10-11 | 原测评面向 15 岁；迁移到本项目年龄只借活动形式，不沿用分数解释 |
| pisa:visual-tool |  | Visual expression domain — the drawing tool（页首续段） | 153 | 155 | 用户定位 + 本机 pdftotext 核对 2026-10-11 | 视觉表达用素材组合式的设计工具（拖放、缩放、旋转、改色），不是自由手绘；本项目改成自由绘画是研究性改编 |
| pisa:dt200q02 |  | Annex C · Science Fair Poster · Question 2/2 (DT200Q02) | — | — | 官方题面图，用户与本机 2026-10-11 都看过；整本 PDF 页码未核 | 「在已有视觉方案上改进」的题型：改进要有原创性、原设计仍可见、一句话描述、建议 5 分钟；官方归为视觉表达领域的「评价与改进」 |
| urban2005:paradigm |  | Design and Construction | 273 | 2 | 用户定位 + 本机 pdftotext 核对 2026-10-11 | 以给定的图形片段为基础完成一幅画；片段刻意做成不完整、不规则以求最大灵活性 |
| ttct:synthesis |  | Interpretive Manual · 5. Synthesis of Incomplete Figures | 4 | 4 | 用户定位 + 本机 pdftotext 核对 2026-10-11 | 辅助来源：评价说明里提到把不完整图形组合起来的表现；不是施测指令 |

原文见 `artquest/taskspace/sources.py`（检查设计依据时读的是原文，不是这里的摘要）。

## 2. 蓝图（任务规格，不是主题列表）

### BP_M1 · 照着参考图把整幅场景重现出来

| 问题 | 回答 |
| --- | --- |
| 适用学段 | 来源：二(3–5)、三(6–7)；拟适用：simple = 小学（课标第二学段：近大远小、写实手法）；full = 初中（第三学段：写实手法、透视；第四学段写实仍在手法清单里） |
| 学习目标 | 观察一个给定场景，按原有位置与大小把整体结构重现出来（整幅、每样东西都在原位） |
| 操作 | observe_represent（观察与表现：看着真实或给定的对象，按其结构 / 关系表现出来）；内容属性：composition, space_perspective |
| 必须提供的输入 | reference: scene（6–8 个可辨识物体、前中后三层）, mode=always；canvas: 空白 |
| 必须保留的产出 | 1 件 · 单幅完整场景 |
| 不能改的条件 | 参考图常显；要求整幅重现、物体在原位；单幅产出 |
| 自由空间 | 线条粗细与风格；是否上色；细节取舍 |
| 负担组成 | compare_schemes=0；spatial_relations=True；read_text=False；modify_existing=False |

来源关系：

| 设计要求 | 关系 | 片段 | 用途（新增条件） |
| --- | --- | --- | --- |
| 观察物体在空间中近大远小、了解透视 | 原文明确规定 | kb:p55:t2-perspective | — |
| 采用写实手法表现 | 原文明确规定 | kb:p55:t2-methods | — |
| 临摹是被承认的模仿与改变原作的手法 | 原文明确规定 | kb:p58:copy-vs-change | — |
| 观察对象从真实空间改成一张给定的场景图（数字画布 + 参考图常显） | 基于来源改编 | kb:p55:t2-perspective | — |
| 「博物馆要重画这幅画」的叙事框架 | 项目新增条件 | — | 给整幅复原一个理由；不改变观察与表现这个操作 |
| 每张场景图 6–8 个物体、三层纵深、无文字无商标 | 项目新增条件 | — | 五张平行卷负荷对齐；合规（无商标） |

### BP_M2 · 看准几样东西的大小、前后与遮挡，画下来

| 问题 | 回答 |
| --- | --- |
| 适用学段 | 来源：二(3–5)、三(6–7)；拟适用：simple = 小学（近大远小）；full = 初中（观察立体物品、透视区别） |
| 学习目标 | 观察少量物体之间的大小差、前后与遮挡关系并准确表现 |
| 操作 | observe_represent（观察与表现：看着真实或给定的对象，按其结构 / 关系表现出来）；内容属性：space_perspective |
| 必须提供的输入 | reference: 桌面静物：正好 4 个物体、正好 2 处遮挡、有大小差、有纵深, mode=always；canvas: 空白 |
| 必须保留的产出 | 1 件 · 单幅观察记录 |
| 不能改的条件 | 参考图常显；4 物体 · 2 遮挡 · 大小差 · 纵深 的规格一个字不能差；单幅产出 |
| 自由空间 | 是否上色；背景是否画；线条风格 |
| 负担组成 | compare_schemes=0；spatial_relations=True；read_text=False；modify_existing=False |

来源关系：

| 设计要求 | 关系 | 片段 | 用途（新增条件） |
| --- | --- | --- | --- |
| 观察物体在空间中近大远小 | 原文明确规定 | kb:p55:t2-perspective | — |
| 从不同角度观察立体物品，了解透视区别 | 原文明确规定 | kb:p60:t2-perspective | — |
| 观察对象改为桌面静物照片 / 插画 | 基于来源改编 | kb:p55:t2-perspective | — |
| 4 物体 · 2 遮挡 · 大小差 · 纵深 | 项目新增条件 | — | 控制空间关系的数量，让五张平行卷可比 |
| 侦探 / 寻宝 / 机器人等叙事 | 项目新增条件 | — | 给记录一个理由；不改变操作 |

### BP_M3 · 把画布上的碎片接着画成一幅完整的画

| 问题 | 回答 |
| --- | --- |
| 适用学段 | 来源：一(1–2)、二(3–5)、三(6–7)；拟适用：simple = 小学（想象力、添加手法）；full = 初中（提出构想并灵活变通） |
| 学习目标 | 以不完整图形为起点进行想象与转化，把碎片整合进一幅完整画面 |
| 操作 | personal_expression（个人表达：按自己的想法用造型元素表达所见所闻所感所想）；内容属性：deformation_methods, composition |
| 必须提供的输入 | reference: 无参考图（明确配置）；canvas: 初始画布印有 7 块矢量碎片（弧、点、线、角、曲线、缺口矩形） |
| 必须保留的产出 | 1 件 · 单幅完整画面，碎片保留在画布上 |
| 不能改的条件 | 碎片印在初始画布上、擦不掉；七块元件种类相同只是摆法不同（A–E 五组平行）；单幅产出 |
| 自由空间 | 用几块碎片；碎片变成什么；主题、颜色 |
| 负担组成 | compare_schemes=0；spatial_relations=False；read_text=False；modify_existing=True |

来源关系：

| 设计要求 | 关系 | 片段 | 用途（新增条件） |
| --- | --- | --- | --- |
| 参考 Urban（2005）第 273 页的图形片段续画范式；本项目自行设计刺激材料和任务实例 | 基于来源改编 | urban2005:paradigm | — |
| 保持好奇心和想象力；添加是被承认的改变原作手法 | 原文明确规定 | kb:p58:copy-vs-change | — |
| 碎片改为画布空间的矢量图元（客户端与回放同一实现） | 项目新增条件 | — | replay = 初始画布 + 笔画；两端逐像素一致 |
| 梦 / 符号 / 壁画等叙事 | 项目新增条件 | — | 给碎片一个来历；不规定碎片要变成什么 |

### BP_M4 · 把一件普通物品改造成另一种用途的东西

| 问题 | 回答 |
| --- | --- |
| 适用学段 | 来源：一(1–2)、三(6–7)；拟适用：simple = 小学（改进生活用品 → 改造，用途由题给）；full = 初中（夸张、变形手法；改造要满足功能条件） |
| 学习目标 | 保留一件物品的部分结构，把它转化为给定环境里的另一种功能物（变形 + 转化） |
| 操作 | purposeful_design（有目的的设计：为一个明确用途 / 功能设计一个方案）；内容属性：deformation_methods |
| 必须提供的输入 | reference: 单件物品图，纯白底, mode=on_demand（默认收起）；canvas: 空白 |
| 必须保留的产出 | 1 件 · 单幅改造后的物品 |
| 不能改的条件 | 基础物品、目标功能（有时还有环境）由题给定；单幅产出 |
| 自由空间 | 保留哪些部分；改造后的外形；是否画环境；颜色 |
| 负担组成 | compare_schemes=0；spatial_relations=False；read_text=False；modify_existing=False |

来源关系：

| 设计要求 | 关系 | 片段 | 用途（新增条件） |
| --- | --- | --- | --- |
| 从外观和功能了解物品，提出改进 | 原文明确规定 | kb:p51:t3-intro | — |
| 夸张、变形手法 | 原文明确规定 | kb:p60:t2-methods | — |
| 「改进」扩展为「改造成另一种功能物」，用途由题指定 | 基于来源改编 | kb:p51:t3-req | — |
| 基础物 × 环境 × 功能 三张卡组合 | 项目新增条件 | — | 平行卷：改变题材、保持操作 |
| 「还要看得出原物」（base_form_preservation） | 项目新增条件 | — | 区分转化与另起炉灶；**只有 M4_J3 的文案写明了它**，其余题只在提示里暗示——见检查结果 |

### BP_M5 · 把两个不相干的概念合成一个新东西

| 问题 | 回答 |
| --- | --- |
| 适用学段 | 来源：三(6–7)、四(8–9)；拟适用：simple = 拟适用小学：题面只要求「合在一起、都能看出来」，不要求归类重组的术语；full = 初中（想象、联想、归类、重组） |
| 学习目标 | 概念整合：两个概念的特征都保留并连成一体，而不是并置 |
| 操作 | personal_expression（个人表达：按自己的想法用造型元素表达所见所闻所感所想）；内容属性：fusion, deformation_methods |
| 必须提供的输入 | reference: 无参考图（明确配置）；canvas: 空白 |
| 必须保留的产出 | 1 件 · 单幅融合物 |
| 不能改的条件 | 两个概念由题给定（ASCII 记进 condition）；要求两者特征都能看出、合为一体；单幅产出 |
| 自由空间 | 哪个概念为主；变成生物 / 建筑 / 交通工具；颜色、场景 |
| 负担组成 | compare_schemes=0；spatial_relations=False；read_text=False；modify_existing=False |

来源关系：

| 设计要求 | 关系 | 片段 | 用途（新增条件） |
| --- | --- | --- | --- |
| 通过想象、联想、归类、重组进行构思 | 原文明确规定 | kb:p68:t2-req | — |
| 提出各种构想并灵活变通 | 原文明确规定 | kb:p61:t2-req | — |
| 概念对由项目挑选、要求「合为一体不是并置」 | 项目新增条件 | — | 把 conceptual integration 和 M4 的单物改造区分开 |

### BP_M6 · 保留场景，只改颜色和明暗，让它有另一种感觉

| 问题 | 回答 |
| --- | --- |
| 适用学段 | 来源：二(3–5)、三(6–7)、四(8–9)；拟适用：simple = 小学（对比色 / 邻近色；冷暖感受）；full = 初中（冷暖、互补、对比；色彩情感特征） |
| 学习目标 | 用颜色与明暗（而不是新增内容）传达指定的气氛 / 温度 / 时间 |
| 操作 | personal_expression（个人表达：按自己的想法用造型元素表达所见所闻所感所想）；内容属性：color |
| 必须提供的输入 | reference: 情绪中性、低饱和的场景图, mode=always；canvas: 空白（孩子在参考图旁重画并改色） |
| 必须保留的产出 | 1 件 · 单幅改色后的场景 |
| 不能改的条件 | 参考图常显；目标气氛由题给定（mood 记进 condition）；只改颜色和明暗、不加新东西；单幅产出 |
| 自由空间 | 具体用哪些颜色；明暗怎么分布；画得多细 |
| 负担组成 | compare_schemes=0；spatial_relations=False；read_text=False；modify_existing=False |

来源关系：

| 设计要求 | 关系 | 片段 | 用途（新增条件） |
| --- | --- | --- | --- |
| 体验不同色彩带来的不同感受；冷暖、互补、对比 | 原文明确规定 | kb:p60:t2-color | — |
| 色彩情感特征 | 原文明确规定 | kb:p68:t2-color | — |
| 对比色、邻近色 | 原文明确规定 | kb:p54:t2-color | — |
| 「只改颜色和明暗、不加新东西」 | 项目新增条件 | — | 把颜色变量从内容变量里隔离出来，让 color richness / contrast 真正可观察 |
| 参考图要情绪中性、低饱和 | 项目新增条件 | — | 原图越平，改动越看得出 |

### BP_M7 · 先只用线条画一个抽象概念，再把这些线发展成一幅画

| 问题 | 回答 |
| --- | --- |
| 适用学段 | 来源：一(1–2)、四(8–9)；拟适用：simple = 小学（线条造型元素；概念是具体可感的：雨、弹跳、生长）；full = 初中（抽象手法；概念更内在：小声说话、沉重、紧张） |
| 学习目标 | 第一步用线条的疏密、方向、力度表达概念；第二步不擦掉这些线，把它们转化成有内容的画 |
| 操作 | personal_expression（个人表达：按自己的想法用造型元素表达所见所闻所感所想）；内容属性：line, deformation_methods |
| 必须提供的输入 | reference: 无参考图（明确配置）；canvas: 空白 |
| 必须保留的产出 | 1 件 · 单幅最终画；第一步的线应保留在画中（由文案要求，不由工具保证） |
| 不能改的条件 | 概念由题给定；第一步只用线条、不画具体物；第二步不擦掉第一步的线；单幅产出 |
| 自由空间 | 线的样子；第二步变成什么；颜色 |
| 负担组成 | compare_schemes=0；spatial_relations=False；read_text=False；modify_existing=True |

来源关系：

| 设计要求 | 关系 | 片段 | 用途（新增条件） |
| --- | --- | --- | --- |
| 线条等造型元素按自己的想法表达 | 原文明确规定 | kb:p50:t2-intro | — |
| 抽象手法 | 原文明确规定 | kb:p68:t2-methods | — |
| 两步结构（先抽象线条，再发展成作品） | 项目新增条件 | — | 把 line combination / texture 和后面的转化分开观察 |
| 「第一步（60 秒）」 | 项目新增条件 | — | 只是引导语：程序不计时、不切换工具（2026-10-05 取消所有限时） |

### BP_M8 · 按给定的两三条世界规则，画出这个世界里的生活

| 问题 | 回答 |
| --- | --- |
| 适用学段 | 来源：三(6–7)、四(8–9)；拟适用：simple = 拟适用小学：规则两条、用词具体（人比虫子小）；full = 初中：固定开头 + 两条 + 一条可选挑战 |
| 学习目标 | 在给定约束下进行接近真实创作的想象与组织（规则必须在画里成立） |
| 操作 | personal_expression（个人表达：按自己的想法用造型元素表达所见所闻所感所想）；内容属性：constraint_rules, composition |
| 必须提供的输入 | reference: 无参考图（明确配置）；canvas: 空白 |
| 必须保留的产出 | 1 件 · 单幅世界场景 |
| 不能改的条件 | 规则由题给定并记进 condition；规则要在画里成立；单幅产出 |
| 自由空间 | 画哪一刻、哪个地方；谁在里面；颜色、风格 |
| 负担组成 | compare_schemes=0；spatial_relations=False；read_text=True；modify_existing=False |

来源关系：

| 设计要求 | 关系 | 片段 | 用途（新增条件） |
| --- | --- | --- | --- |
| 想象、联想、重组 | 原文明确规定 | kb:p68:t2-req | — |
| 「科学幻想」是课标列出的情境素材举例 | 原文明确规定 | kb:p66:contexts | — |
| 世界规则生成器（两三条规则） | 项目新增条件 | — | 用可记录的约束替代自由命题，让 rule_coverage 可比 |
| 初中版可选第三条 | 项目新增条件 | — | 给负担留一个可选台阶；可选项不进必要产出 |

### BP_M9 · 给一个故事开头，画出接下来发生的事

| 问题 | 回答 |
| --- | --- |
| 适用学段 | 来源：一(1–2)、二(3–5)、三(6–7)；拟适用：simple = 小学；full = 初中 |
| 学习目标 | 生态效度基线：受控任务里看到的行为模式，在接近真实的创作里还在吗 |
| 操作 | personal_expression（个人表达：按自己的想法用造型元素表达所见所闻所感所想）；内容属性：narrative, composition |
| 必须提供的输入 | reference: 无参考图（明确配置）；canvas: 空白 |
| 必须保留的产出 | 1 件 · 单幅叙事画面 |
| 不能改的条件 | 故事开头由题给定；单幅产出 |
| 自由空间 | 画哪一刻；有谁、在哪；颜色、风格 |
| 负担组成 | compare_schemes=0；spatial_relations=False；read_text=False；modify_existing=False |

来源关系：

| 设计要求 | 关系 | 片段 | 用途（新增条件） |
| --- | --- | --- | --- |
| 表达所见所闻、所感所想 | 原文明确规定 | kb:p54:t2-intro | — |
| 「校园中的故事」是课标列出的情境素材举例 | 原文明确规定 | kb:p66:contexts | — |
| 故事开头由项目给定 | 项目新增条件 | — | 让不同孩子的画可比，同时保持开放 |

### BP_M0 · 自由创作（v1 基线，legacy）

| 问题 | 回答 |
| --- | --- |
| 适用学段 | 来源：—；拟适用：simple = —；full = — |
| 学习目标 | 开放创作基线：每个研究字段取宽松值 |
| 操作 | personal_expression（个人表达：按自己的想法用造型元素表达所见所闻所感所想）；内容属性：— |
| 必须提供的输入 | reference: 无；canvas: 空白 |
| 必须保留的产出 | 1 件 · 单幅 |
| 不能改的条件 | 旧 id 不改 |
| 自由空间 | 一切 |
| 负担组成 | compare_schemes=0；spatial_relations=False；read_text=False；modify_existing=False |

来源关系：

| 设计要求 | 关系 | 片段 | 用途（新增条件） |
| --- | --- | --- | --- |
| 表达所见所闻、所感所想 | 原文明确规定 | kb:p50:t2-intro | — |

### BP_OB · 首访 · 观察与表现：看着参考图画出对象及其关系

| 问题 | 回答 |
| --- | --- |
| 适用学段 | 来源：一(1–2)、二(3–5)、三(6–7)、四(8–9)、高中起始、17+（无学段，取自 M 族题库）；拟适用：simple = None；full = None |
| 学习目标 | 用共同参考比较外形与关系；复杂度按对象数和关系数描述，不是实测难度 |
| 操作 | observe_represent（观察与表现：看着真实或给定的对象，按其结构 / 关系表现出来）；内容属性：space_perspective, line |
| 必须提供的输入 | reference: 单张参考 PNG（1600×1200），always，contain；canvas: 空白 |
| 必须保留的产出 | 1 件 · 单幅观察画 |
| 不能改的条件 | 参考图常显且完整显示；题面点名的对象和关系要出现；单幅产出；允许单色 |
| 自由空间 | 线稿或上色；整体大小；省略细节 |
| 负担组成 | compare_schemes=0；spatial_relations=True；read_text=False；modify_existing=False |

来源关系：

| 设计要求 | 关系 | 片段 | 用途（新增条件） |
| --- | --- | --- | --- |
| 观察自然 / 生活对象的形状、色彩、肌理；近大远小与透视 | 原文明确规定 | kb:p49:t1-nature | — |
| 观察空间中的近大远小 | 原文明确规定 | kb:p55:t2-perspective | — |
| 观察对象改为参考图而非实物 | 基于来源改编 | kb:p55:t2-perspective | — |
| 全部任务从空白画布开始，提交一幅作品；参考图在参考区常显、不粘贴进作品 | 项目新增条件 | — | first_visit_common_v1：首稿一幅、材料不混入作品 |
| 参考 PNG 1600×1200、contain 完整显示，不裁掉叶柄 / 车轮 / 笔筒底 | 项目新增条件 | — | 材料条件：孩子看到的就是检查过的那张 |
| 没有 60 秒阶段、不限时；提示固定、按需显示、记显示事件 | 项目新增条件 | — | 提示是过程支持，不产生新的必须条件 |
| 允许单色、不要求写字；首访不开修改轮 | 项目新增条件 | — | 颜色丰富度和文字长度不是通用完成门槛 |

### BP_ST · 首访 · 个人表达与叙事：一幅画表现一件事或一种理解

| 问题 | 回答 |
| --- | --- |
| 适用学段 | 来源：一(1–2)、二(3–5)、三(6–7)、四(8–9)、高中起始、17+（无学段，取自 M 族题库）；拟适用：simple = None；full = None |
| 学习目标 | 用形象、动作、布局表达一个生活 / 想象情境或一个概念；单幅、不写故事 |
| 操作 | personal_expression（个人表达：按自己的想法用造型元素表达所见所闻所感所想）；内容属性：narrative, composition |
| 必须提供的输入 | reference: 无参考图（明确配置）；canvas: 空白 |
| 必须保留的产出 | 1 件 · 单幅叙事 / 表达画 |
| 不能改的条件 | 单幅；题面要求的人物 / 动作 / 对比要出现；不要求写字 |
| 自由空间 | 真实或想象；颜色、背景；人物画法 |
| 负担组成 | compare_schemes=0；spatial_relations=False；read_text=False；modify_existing=False |

来源关系：

| 设计要求 | 关系 | 片段 | 用途（新增条件） |
| --- | --- | --- | --- |
| 按自己的想法表达所见所闻所感所想 | 原文明确规定 | kb:p50:t2-intro | — |
| 表现自己的所见所闻、所感所想，以视觉形象与人交流 | 原文明确规定 | kb:p54:t2-intro | — |
| 创造性地表达对自然与社会的感受、思考和认识 | 原文明确规定 | kb:p68:t2-intro | — |
| 全部任务从空白画布开始，提交一幅作品；参考图在参考区常显、不粘贴进作品 | 项目新增条件 | — | first_visit_common_v1：首稿一幅、材料不混入作品 |
| 参考 PNG 1600×1200、contain 完整显示，不裁掉叶柄 / 车轮 / 笔筒底 | 项目新增条件 | — | 材料条件：孩子看到的就是检查过的那张 |
| 没有 60 秒阶段、不限时；提示固定、按需显示、记显示事件 | 项目新增条件 | — | 提示是过程支持，不产生新的必须条件 |
| 允许单色、不要求写字；首访不开修改轮 | 项目新增条件 | — | 颜色丰富度和文字长度不是通用完成门槛 |

### BP_FG · 首访 · 图形片段创作：把参考区的原创片段画进一幅画并发展它

| 问题 | 回答 |
| --- | --- |
| 适用学段 | 来源：一(1–2)、二(3–5)、三(6–7)、四(8–9)、高中起始、17+（无学段，取自 M 族题库）；拟适用：simple = None；full = None |
| 学习目标 | 从模糊图形刺激发展个人构想；片段在参考区，由孩子转抄到空白画布（不印在画布上，不是 TCT-DP 原题） |
| 操作 | personal_expression（个人表达：按自己的想法用造型元素表达所见所闻所感所想）；内容属性：deformation_methods, composition |
| 必须提供的输入 | reference: 片段参考 PNG（+ 可编辑 SVG），always，contain；canvas: 空白 |
| 必须保留的产出 | 1 件 · 单幅画，原片段仍能被找到 |
| 不能改的条件 | 所有片段都要能找到；可移动 / 旋转 / 缩放；单幅 |
| 自由空间 | 片段变成什么；主题；颜色 |
| 负担组成 | compare_schemes=0；spatial_relations=False；read_text=False；modify_existing=False |

来源关系：

| 设计要求 | 关系 | 片段 | 用途（新增条件） |
| --- | --- | --- | --- |
| 以给定的图形片段为基础完成一幅画 | 基于来源改编 | urban2005:paradigm | — |
| 保持好奇心和想象力；添加是被承认的改变手法 | 原文明确规定 | kb:p58:copy-vs-change | — |
| 片段原创、参考区呈现、自由手绘转抄（和 M3 印在画布上不同） | 项目新增条件 | — | 不复制原测验题纸、边框、计时或评分；转抄是额外的操作负担，分析时记着 |
| 全部任务从空白画布开始，提交一幅作品；参考图在参考区常显、不粘贴进作品 | 项目新增条件 | — | first_visit_common_v1：首稿一幅、材料不混入作品 |
| 参考 PNG 1600×1200、contain 完整显示，不裁掉叶柄 / 车轮 / 笔筒底 | 项目新增条件 | — | 材料条件：孩子看到的就是检查过的那张 |
| 没有 60 秒阶段、不限时；提示固定、按需显示、记显示事件 | 项目新增条件 | — | 提示是过程支持，不产生新的必须条件 |
| 允许单色、不要求写字；首访不开修改轮 | 项目新增条件 | — | 颜色丰富度和文字长度不是通用完成门槛 |

### BP_TR · 首访 · 物品创意改造：把参考物品变成有新用途的东西并保留可辨认特征

| 问题 | 回答 |
| --- | --- |
| 适用学段 | 来源：一(1–2)、二(3–5)、三(6–7)、四(8–9)、高中起始、17+（无学段，取自 M 族题库）；拟适用：simple = None；full = None |
| 学习目标 | 把熟悉物品的特征和一个新用途联系起来；「保留可辨认特征」写在题面里，不是隐藏要求 |
| 操作 | purposeful_design（有目的的设计：为一个明确用途 / 功能设计一个方案）；内容属性：deformation_methods |
| 必须提供的输入 | reference: 单件物品 PNG，always，contain（参考图不含改造答案）；canvas: 空白 |
| 必须保留的产出 | 1 件 · 单幅改造物 + 使用方式 |
| 不能改的条件 | 从参考物品出发；画出怎样使用 / 帮忙；保留可辨认特征（不指定部件）；单幅 |
| 自由空间 | 用途现实或幻想；保留哪些部分；是否画场景 |
| 负担组成 | compare_schemes=0；spatial_relations=False；read_text=False；modify_existing=False |

来源关系：

| 设计要求 | 关系 | 片段 | 用途（新增条件） |
| --- | --- | --- | --- |
| 从外观和功能了解物品，提出改进 | 原文明确规定 | kb:p51:t3-intro | — |
| 夸张、变形手法 | 原文明确规定 | kb:p60:t2-methods | — |
| 「改进」扩展为「改造成新用途」，用途由题给定或由孩子选 | 基于来源改编 | kb:p51:t3-req | — |
| 全部任务从空白画布开始，提交一幅作品；参考图在参考区常显、不粘贴进作品 | 项目新增条件 | — | first_visit_common_v1：首稿一幅、材料不混入作品 |
| 参考 PNG 1600×1200、contain 完整显示，不裁掉叶柄 / 车轮 / 笔筒底 | 项目新增条件 | — | 材料条件：孩子看到的就是检查过的那张 |
| 没有 60 秒阶段、不限时；提示固定、按需显示、记显示事件 | 项目新增条件 | — | 提示是过程支持，不产生新的必须条件 |
| 允许单色、不要求写字；首访不开修改轮 | 项目新增条件 | — | 颜色丰富度和文字长度不是通用完成门槛 |

### BP_DS · 首访 · 视觉传达设计：为一个明确用途做标志 / 吉祥物 / 海报

| 问题 | 回答 |
| --- | --- |
| 适用学段 | 来源：一(1–2)、二(3–5)、三(6–7)、四(8–9)、高中起始、17+（无学段，取自 M 族题库）；拟适用：simple = None；full = None |
| 学习目标 | 让图像为一个明确用途服务；不要求文字、不要求真实校名日期 |
| 操作 | purposeful_design（有目的的设计：为一个明确用途 / 功能设计一个方案）；内容属性：composition |
| 必须提供的输入 | reference: 无参考图（明确配置）；canvas: 空白 |
| 必须保留的产出 | 1 件 · 单幅标志 / 吉祥物 / 海报 |
| 不能改的条件 | 回应题面给定的用途；单幅；不要求写字 |
| 自由空间 | 图形、颜色；是否加标题；角色类型 |
| 负担组成 | compare_schemes=0；spatial_relations=False；read_text=False；modify_existing=False |

来源关系：

| 设计要求 | 关系 | 片段 | 用途（新增条件） |
| --- | --- | --- | --- |
| 为班级或学校的活动设计标识、请柬、贺卡、图表、海报 | 原文明确规定 | kb:p56:t3-visual-design | — |
| 用画笔或计算机做有明确用途的小设计 | 原文明确规定 | kb:p52:t5-design | — |
| 根据不同活动的需要设计海报、请柬 | 原文明确规定 | kb:p62:t3-improve | — |
| 围绕目的形成视觉构想（PISA 只借思路，不沿用分数） | 基于来源改编 | pisa:processes | — |
| 全部任务从空白画布开始，提交一幅作品；参考图在参考区常显、不粘贴进作品 | 项目新增条件 | — | first_visit_common_v1：首稿一幅、材料不混入作品 |
| 参考 PNG 1600×1200、contain 完整显示，不裁掉叶柄 / 车轮 / 笔筒底 | 项目新增条件 | — | 材料条件：孩子看到的就是检查过的那张 |
| 没有 60 秒阶段、不限时；提示固定、按需显示、记显示事件 | 项目新增条件 | — | 提示是过程支持，不产生新的必须条件 |
| 允许单色、不要求写字；首访不开修改轮 | 项目新增条件 | — | 颜色丰富度和文字长度不是通用完成门槛 |

### 2.x 覆盖与缺口

| 操作 \ 来源学段 | 一(1–2) | 二(3–5) | 三(6–7) | 四(8–9) |
| --- | --- | --- | --- | --- |
| observe_represent | BP_OB | BP_M1, BP_M2, BP_OB | BP_M1, BP_M2, BP_OB | BP_OB |
| personal_expression | BP_M3, BP_M7, BP_M9, BP_ST, BP_FG | BP_M3, BP_M6, BP_M9, BP_ST, BP_FG | BP_M3, BP_M5, BP_M6, BP_M8, BP_M9, BP_ST, BP_FG | BP_M5, BP_M6, BP_M7, BP_M8, BP_ST, BP_FG |
| purposeful_design | BP_M4, BP_TR, BP_DS | BP_TR, BP_DS | BP_M4, BP_TR, BP_DS | BP_TR, BP_DS |
| diverse_ideation | — | — | — | — |
| evaluate_improve | — | — | — | — |

课标里有、本库没有蓝图的（保留缺口比用相似题填满更有用）：

| 操作 | 依据片段 | 为什么没有 | 需要的能力 | 备注 |
| --- | --- | --- | --- | --- |
| diverse_ideation | kb:p55:t2-req, kb:p61:t2-req, pisa:processes | 没有任何家族要求产出多个方案；产品也没有一局保存多张草图的能力（CAPABILITIES.multi_sketch_output=False） | multi_sketch_output | PISA 的「产生多样构想」依据尚未录入原文 |
| evaluate_improve | kb:p55:t3-improve, kb:p62:t3-improve, pisa:dt200q02 | 没有「起始作品」类材料，也不能移动起始画面上的对象；M3 碎片是起点不是待改进的方案 | editable_starting_artwork, movable_objects | DT200Q02 原文未录入 |
| purposeful_design | kb:p56:t3-visual-design, kb:p52:t5-design | 校园情境的视觉设计（标识 / 海报 / 请柬）没有蓝图；M4 的「有目的的设计」是物品改造，不是校园视觉设计 | 现有能力已够 | 可以直接起草：空白画布 + 单幅产出 + 无参考图，现有能力已够；示例规格见 docs/任务初始化.md |
| observe_represent | kb:p49:t1-nature | 观察自然对象的形状 / 色彩 / 肌理（第一学段）没有蓝图；M1/M2 的对象都是室内外人造场景或静物 | 现有能力已够 | 需要新的参考图材料规格 |

## 3. 候选（库里 80 道 v2 题，每道都回到蓝图）

状态：`clear` = 规定范围内没发现未解决的一致性问题（**不是已校准**）；`open` = 有无法判断 / 依据不足的项；`blocked` = 有明确矛盾。

### M0 → BP_M0

| task_id | 版本 | 题 | 相对锚定题改变了 | 九维关联（* = 可合理绕开） | 实例级降级（2026-10-11） | 材料 → 检查 | 状态 | 未决问题 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M0_A1 | simple/full·锚 | 超能力 | 锚定题 |  | — | 无参考图（明确配置） | clear | — |
| M0_A2 | simple/full·锚 | 没有轮子的车 | 题材 / 叙事 |  | — | 无参考图（明确配置） | clear | — |
| M0_E3 | simple | 怪兽餐厅 | 题材 / 叙事；版本 ['simple'] |  | — | 无参考图（明确配置） | clear | — |
| M0_E4 | simple | 食物的心情 | 题材 / 叙事；版本 ['simple'] |  | — | 无参考图（明确配置） | clear | — |
| M0_E5 | simple | 游戏最后一关 | 题材 / 叙事；版本 ['simple'] |  | — | 无参考图（明确配置） | clear | — |
| M0_J3 | full | 海底城市 | 题材 / 叙事；版本 ['full'] |  | — | 无参考图（明确配置） | clear | — |
| M0_J4 | full | 机器人和植物 | 题材 / 叙事；版本 ['full'] |  | — | 无参考图（明确配置） | clear | — |
| M0_J5 | full | 夜晚的体育馆 | 题材 / 叙事；版本 ['full'] |  | — | 无参考图（明确配置） | clear | — |

### M1 → BP_M1

| task_id | 版本 | 题 | 相对锚定题改变了 | 九维关联（* = 可合理绕开） | 实例级降级（2026-10-11） | 材料 → 检查 | 状态 | 未决问题 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M1_A1 | simple/full·锚 | 教室 | 锚定题 | realism, picture_organization, line_combination | line_texture→exploratory | m1_scene_e（always）→ 无法判断 | clear | — |
| M1_A2 | simple/full·锚 | 书桌 | 材料；题材 / 叙事 | realism, picture_organization, line_combination | line_texture→exploratory | m1_scene_c（always）→ 无法判断 | clear | — |
| M1_E3 | simple | 营地 | 材料；题材 / 叙事；版本 ['simple'] | realism, picture_organization, line_combination | line_texture→exploratory | m1_scene_b（always）→ 无法判断 | clear | — |
| M1_E4 | simple | 小猫的家 | 材料；题材 / 叙事；版本 ['simple'] | realism, picture_organization, line_combination | line_texture→exploratory | m1_scene_a（always）→ 无法判断 | clear | — |
| M1_E5 | simple | 公园 | 材料；题材 / 叙事；版本 ['simple'] | realism, picture_organization, line_combination | line_texture→exploratory | m1_scene_d（always）→ 无法判断 | clear | — |
| M1_J3 | full | 无人机的图 | 材料；题材 / 叙事；版本 ['full'] | realism, picture_organization, line_combination | line_texture→exploratory | m1_scene_d（always）→ 无法判断 | clear | — |
| M1_J4 | full | 营地记录 | 材料；题材 / 叙事；版本 ['full'] | realism, picture_organization, line_combination | line_texture→exploratory | m1_scene_b（always）→ 无法判断 | clear | — |
| M1_J5 | full | 重画这幅画 | 材料；题材 / 叙事；版本 ['full'] | realism, picture_organization, line_combination | line_texture→exploratory | m1_scene_a（always）→ 无法判断 | clear | — |

### M2 → BP_M2

| task_id | 版本 | 题 | 相对锚定题改变了 | 九维关联（* = 可合理绕开） | 实例级降级（2026-10-11） | 材料 → 检查 | 状态 | 未决问题 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M2_A1 | simple/full·锚 | 桌上的机器人 | 锚定题 | realism, picture_organization, line_combination | line_texture→exploratory | m2_scene_a（always）→ 无法判断 | clear | — |
| M2_A2 | simple/full·锚 | 帮机器人看图 | 材料；题材 / 叙事 | realism, picture_organization, line_combination | line_texture→exploratory | m2_scene_b（always）→ 无法判断 | clear | — |
| M2_E3 | simple | 玩具清单 | 材料；题材 / 叙事；版本 ['simple'] | realism, picture_organization, line_combination | line_texture→exploratory | m2_scene_d（always）→ 无法判断 | clear | — |
| M2_E4 | simple | 寻宝记录 | 材料；题材 / 叙事；版本 ['simple'] | realism, picture_organization, line_combination | line_texture→exploratory | m2_scene_c（always）→ 无法判断 | clear | — |
| M2_E5 | simple | 侦探笔记 | 材料；题材 / 叙事；版本 ['simple'] | realism, picture_organization, line_combination | line_texture→exploratory | m2_scene_e（always）→ 无法判断 | clear | — |
| M2_J3 | full | 桌上的记录 | 材料；题材 / 叙事；版本 ['full'] | realism, picture_organization, line_combination | line_texture→exploratory | m2_scene_d（always）→ 无法判断 | clear | — |
| M2_J4 | full | 速写 | 材料；题材 / 叙事；版本 ['full'] | realism, picture_organization, line_combination | line_texture→exploratory | m2_scene_e（always）→ 无法判断 | clear | — |
| M2_J5 | full | 博物馆里的物品 | 材料；题材 / 叙事；版本 ['full'] | realism, picture_organization, line_combination | line_texture→exploratory | m2_scene_c（always）→ 无法判断 | clear | — |

### M3 → BP_M3

| task_id | 版本 | 题 | 相对锚定题改变了 | 九维关联（* = 可合理绕开） | 实例级降级（2026-10-11） | 材料 → 检查 | 状态 | 未决问题 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M3_A1 | simple/full·锚 | 梦里的画 | 锚定题 | imagination, transformation, picture_organization | deformation→exploratory, line_combination→exploratory | m3_fragments_a（fragments）→ 符合 | clear | — |
| M3_A2 | simple/full·锚 | 符号变成画 | 材料；condition.fragment_seed；题材 / 叙事 | imagination, transformation, picture_organization | deformation→exploratory, line_combination→exploratory | m3_fragments_b（fragments）→ 符合 | clear | — |
| M3_E3 | simple | 云里有什么 | 材料；condition.fragment_seed；题材 / 叙事；版本 ['simple'] | imagination, transformation, picture_organization | deformation→exploratory, line_combination→exploratory | m3_fragments_c（fragments）→ 符合 | clear | — |
| M3_E4 | simple | 画完这幅画 | 材料；condition.fragment_seed；题材 / 叙事；版本 ['simple'] | imagination, transformation, picture_organization | deformation→exploratory, line_combination→exploratory | m3_fragments_d（fragments）→ 符合 | clear | — |
| M3_E5 | simple | 拼一幅画 | 材料；condition.fragment_seed；题材 / 叙事；版本 ['simple'] | imagination, transformation, picture_organization | deformation→exploratory, line_combination→exploratory | m3_fragments_e（fragments）→ 符合 | clear | — |
| M3_J3 | full | 补全画面 | 材料；condition.fragment_seed；题材 / 叙事；版本 ['full'] | imagination, transformation, picture_organization | deformation→exploratory, line_combination→exploratory | m3_fragments_c（fragments）→ 符合 | clear | — |
| M3_J4 | full | 壁画 | 材料；condition.fragment_seed；题材 / 叙事；版本 ['full'] | imagination, transformation, picture_organization | deformation→exploratory, line_combination→exploratory | m3_fragments_d（fragments）→ 符合 | clear | — |
| M3_J5 | full | 补画机器 | 材料；condition.fragment_seed；题材 / 叙事；版本 ['full'] | imagination, transformation, picture_organization | deformation→exploratory, line_combination→exploratory | m3_fragments_e（fragments）→ 符合 | clear | — |

### M4 → BP_M4

| task_id | 版本 | 题 | 相对锚定题改变了 | 九维关联（* = 可合理绕开） | 实例级降级（2026-10-11） | 材料 → 检查 | 状态 | 未决问题 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M4_A1 | simple/full·锚 | 雨伞变潜水艇 | 锚定题 | deformation, transformation, imagination | picture_organization→exploratory, line_combination→exploratory | m4_umbrella（on_demand）→ 无法判断 | clear | — |
| M4_A2 | simple/full·锚 | 改造书包 | 材料；condition.base_object；condition.environment；condition.goal；题材 / 叙事 | deformation, transformation, imagination | picture_organization→exploratory, line_combination→exploratory | m4_backpack（on_demand）→ 无法判断 | clear | — |
| M4_E3 | simple | 椅子变宠物 | 材料；condition.base_object；condition.environment；condition.goal；题材 / 叙事；版本 ['simple'] | deformation, transformation, imagination | picture_organization→exploratory, line_combination→exploratory | m4_chair（on_demand）→ 无法判断 | clear | — |
| M4_E4 | simple | 茶壶变火箭 | 材料；condition.base_object；condition.environment；题材 / 叙事；版本 ['simple'] | deformation, transformation, imagination | picture_organization→exploratory, line_combination→exploratory | m4_teapot（on_demand）→ 无法判断 | clear | — |
| M4_E5 | simple | 时钟变车 | 材料；condition.base_object；condition.environment；题材 / 叙事；版本 ['simple'] | deformation, transformation, imagination | picture_organization→exploratory, line_combination→exploratory | m4_clock（on_demand）→ 无法判断 | clear | — |
| M4_J3 | full | 鞋子变生物 | 材料；condition.base_object；condition.environment；condition.goal；题材 / 叙事；版本 ['full'] | deformation, transformation, imagination | picture_organization→exploratory, line_combination→exploratory | m4_shoe（on_demand）→ 无法判断 | clear | — |
| M4_J4 | full | 茶壶救援机 | 材料；condition.base_object；condition.environment；condition.goal；题材 / 叙事；版本 ['full'] | deformation, transformation, imagination | picture_organization→exploratory, line_combination→exploratory | m4_teapot（on_demand）→ 无法判断 | clear | — |
| M4_J5 | full | 自行车变机甲 | 材料；condition.base_object；condition.environment；condition.goal；题材 / 叙事；版本 ['full'] | deformation, transformation, imagination | picture_organization→exploratory, line_combination→exploratory | m4_bicycle（on_demand）→ 不符合 | clear | — |

### M5 → BP_M5

| task_id | 版本 | 题 | 相对锚定题改变了 | 九维关联（* = 可合理绕开） | 实例级降级（2026-10-11） | 材料 → 检查 | 状态 | 未决问题 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M5_A1 | simple/full·锚 | 城堡 + 水母 | 锚定题 | transformation, deformation, imagination | picture_organization→exploratory | 无参考图（明确配置） | clear | — |
| M5_A2 | simple/full·锚 | 机器人 + 花 | condition.concept_a；condition.concept_b；题材 / 叙事 | transformation, deformation, imagination | picture_organization→exploratory | 无参考图（明确配置） | clear | — |
| M5_E3 | simple | 狐狸 + 火车 | condition.concept_a；condition.concept_b；题材 / 叙事；版本 ['simple'] | transformation, deformation, imagination | picture_organization→exploratory | 无参考图（明确配置） | clear | — |
| M5_E4 | simple | 鲨鱼 + 书包 | condition.concept_a；condition.concept_b；题材 / 叙事；版本 ['simple'] | transformation, deformation, imagination | picture_organization→exploratory | 无参考图（明确配置） | clear | — |
| M5_E5 | simple | 蛋糕 + 房子 | condition.concept_a；condition.concept_b；题材 / 叙事；版本 ['simple'] | transformation, deformation, imagination | picture_organization→exploratory | 无参考图（明确配置） | clear | — |
| M5_J3 | full | 时钟 + 章鱼 | condition.concept_a；condition.concept_b；题材 / 叙事；版本 ['full'] | transformation, deformation, imagination | picture_organization→exploratory | 无参考图（明确配置） | clear | — |
| M5_J4 | full | 地铁 + 龙 | condition.concept_a；condition.concept_b；题材 / 叙事；版本 ['full'] | transformation, deformation, imagination | picture_organization→exploratory | 无参考图（明确配置） | clear | — |
| M5_J5 | full | 鲸鱼 + 学校 | condition.concept_a；condition.concept_b；题材 / 叙事；版本 ['full'] | transformation, deformation, imagination | picture_organization→exploratory | 无参考图（明确配置） | clear | — |

### M6 → BP_M6

| task_id | 版本 | 题 | 相对锚定题改变了 | 九维关联（* = 可合理绕开） | 实例级降级（2026-10-11） | 材料 → 检查 | 状态 | 未决问题 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M6_A1 | simple/full·锚 | 夜晚 | 锚定题 | color_richness, color_contrast | picture_organization→exploratory, line_texture→exploratory | m6_scene_a（always）→ 无法判断 | clear | — |
| M6_A2 | simple/full·锚 | 吓人的地方 | 材料；condition.mood；题材 / 叙事 | color_richness, color_contrast | picture_organization→exploratory, line_texture→exploratory | m6_scene_d（always）→ 无法判断 | clear | — |
| M6_E3 | simple | 寒冷 | 材料；condition.mood；题材 / 叙事；版本 ['simple'] | color_richness, color_contrast | picture_organization→exploratory, line_texture→exploratory | m6_scene_c（always）→ 无法判断 | clear | — |
| M6_E4 | simple | 热闹 | 材料；condition.mood；题材 / 叙事；版本 ['simple'] | color_richness, color_contrast | picture_organization→exploratory, line_texture→exploratory | m6_scene_b（always）→ 无法判断 | clear | — |
| M6_E5 | simple | 温暖 | 材料；condition.mood；题材 / 叙事；版本 ['simple'] | color_richness, color_contrast | picture_organization→exploratory, line_texture→exploratory | m6_scene_e（always）→ 无法判断 | clear | — |
| M6_J3 | full | 神秘 | 材料；condition.mood；题材 / 叙事；版本 ['full'] | color_richness, color_contrast | picture_organization→exploratory, line_texture→exploratory | m6_scene_e（always）→ 无法判断 | clear | — |
| M6_J4 | full | 暴风雨要来了 | 材料；condition.mood；题材 / 叙事；版本 ['full'] | color_richness, color_contrast | picture_organization→exploratory, line_texture→exploratory | m6_scene_b（always）→ 无法判断 | clear | — |
| M6_J5 | full | 安全和危险 | 材料；condition.mood；题材 / 叙事；版本 ['full'] | color_richness, color_contrast | picture_organization→exploratory, line_texture→exploratory | m6_scene_c（always）→ 无法判断 | clear | — |

### M7 → BP_M7

| task_id | 版本 | 题 | 相对锚定题改变了 | 九维关联（* = 可合理绕开） | 实例级降级（2026-10-11） | 材料 → 检查 | 状态 | 未决问题 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M7_A1 | simple/full·锚 | 风 | 锚定题 | line_combination, line_texture, transformation, imagination | picture_organization→exploratory | 无参考图（明确配置） | clear | — |
| M7_A2 | simple/full·锚 | 速度 | condition.concept；题材 / 叙事 | line_combination, line_texture, transformation, imagination | picture_organization→exploratory | 无参考图（明确配置） | clear | — |
| M7_E3 | simple | 雨 | condition.concept；题材 / 叙事；版本 ['simple'] | line_combination, line_texture, transformation, imagination | picture_organization→exploratory | 无参考图（明确配置） | clear | — |
| M7_E4 | simple | 弹跳 | condition.concept；题材 / 叙事；版本 ['simple'] | line_combination, line_texture, transformation, imagination | picture_organization→exploratory | 无参考图（明确配置） | clear | — |
| M7_E5 | simple | 生长 | condition.concept；题材 / 叙事；版本 ['simple'] | line_combination, line_texture, transformation, imagination | picture_organization→exploratory | 无参考图（明确配置） | clear | — |
| M7_J3 | full | 小声说话 | condition.concept；题材 / 叙事；版本 ['full'] | line_combination, line_texture, transformation, imagination | picture_organization→exploratory | 无参考图（明确配置） | clear | — |
| M7_J4 | full | 沉重 | condition.concept；题材 / 叙事；版本 ['full'] | line_combination, line_texture, transformation, imagination | picture_organization→exploratory | 无参考图（明确配置） | clear | — |
| M7_J5 | full | 紧张 | condition.concept；题材 / 叙事；版本 ['full'] | line_combination, line_texture, transformation, imagination | picture_organization→exploratory | 无参考图（明确配置） | clear | — |

### M8 → BP_M8

| task_id | 版本 | 题 | 相对锚定题改变了 | 九维关联（* = 可合理绕开） | 实例级降级（2026-10-11） | 材料 → 检查 | 状态 | 未决问题 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M8_A1 | simple/full·锚 | 云上的城市 | 锚定题 | imagination, transformation, picture_organization | realism→exploratory, deformation→exploratory, color_richness→exploratory, color_contrast→exploratory, line_combination→exploratory, line_texture→exploratory | 无参考图（明确配置） | clear | — |
| M8_A2 | simple/full·锚 | 会走的影子 | condition.rules；题材 / 叙事 | imagination, transformation, picture_organization | realism→exploratory, deformation→exploratory, color_richness→exploratory, color_contrast→exploratory, line_combination→exploratory, line_texture→exploratory | 无参考图（明确配置） | clear | — |
| M8_E3 | simple | 人变小了 | condition.rules；题材 / 叙事；版本 ['simple'] | imagination, transformation, picture_organization, deformation | realism→exploratory, color_richness→exploratory, color_contrast→exploratory, line_combination→exploratory, line_texture→exploratory | 无参考图（明确配置） | clear | — |
| M8_E4 | simple | 水在天上 | condition.rules；题材 / 叙事；版本 ['simple'] | imagination, transformation, picture_organization | realism→exploratory, deformation→exploratory, color_richness→exploratory, color_contrast→exploratory, line_combination→exploratory, line_texture→exploratory | 无参考图（明确配置） | clear | — |
| M8_E5 | simple | 树里的世界 | condition.rules；题材 / 叙事；版本 ['simple'] | imagination, transformation, picture_organization, deformation | realism→exploratory, color_richness→exploratory, color_contrast→exploratory, line_combination→exploratory, line_texture→exploratory | 无参考图（明确配置） | clear | — |
| M8_J3 | full | 往旁边掉 | condition.challenge；condition.rules；题材 / 叙事；版本 ['full'] | imagination, transformation, picture_organization, deformation | realism→exploratory, color_richness→exploratory, color_contrast→exploratory, line_combination→exploratory, line_texture→exploratory | 无参考图（明确配置） | clear | — |
| M8_J4 | full | 水下的城市 | condition.challenge；condition.rules；题材 / 叙事；版本 ['full'] | imagination, transformation, picture_organization | realism→exploratory, deformation→exploratory, color_richness→exploratory, color_contrast→exploratory, line_combination→exploratory, line_texture→exploratory | 无参考图（明确配置） | clear | — |
| M8_J5 | full | 动物的城市 | condition.challenge；condition.rules；题材 / 叙事；版本 ['full'] | imagination, transformation, picture_organization, deformation | realism→exploratory, color_richness→exploratory, color_contrast→exploratory, line_combination→exploratory, line_texture→exploratory | 无参考图（明确配置） | clear | — |

### M9 → BP_M9

| task_id | 版本 | 题 | 相对锚定题改变了 | 九维关联（* = 可合理绕开） | 实例级降级（2026-10-11） | 材料 → 检查 | 状态 | 未决问题 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M9_A1 | simple/full·锚 | 学校的新门 | 锚定题 | imagination, picture_organization | transformation→exploratory, color_richness→exploratory, line_combination→exploratory | 无参考图（明确配置） | clear | — |
| M9_A2 | simple/full·锚 | 没变小的东西 | 题材 / 叙事 | imagination, picture_organization | transformation→exploratory, color_richness→exploratory, line_combination→exploratory | 无参考图（明确配置） | clear | — |
| M9_E3 | simple | 会说话的课桌 | 题材 / 叙事；版本 ['simple'] | imagination, picture_organization | transformation→exploratory, color_richness→exploratory, line_combination→exploratory | 无参考图（明确配置） | clear | — |
| M9_E4 | simple | 鲨鱼上学 | 题材 / 叙事；版本 ['simple'] | imagination, picture_organization | transformation→exploratory, color_richness→exploratory, line_combination→exploratory | 无参考图（明确配置） | clear | — |
| M9_E5 | simple | 宠物的超能力 | 题材 / 叙事；版本 ['simple'] | imagination, picture_organization | transformation→exploratory, color_richness→exploratory, line_combination→exploratory | 无参考图（明确配置） | clear | — |
| M9_J3 | full | 教室里少了东西 | 题材 / 叙事；版本 ['full'] | imagination, picture_organization | transformation→exploratory, color_richness→exploratory, line_combination→exploratory | 无参考图（明确配置） | clear | — |
| M9_J4 | full | 火星便利店 | 题材 / 叙事；版本 ['full'] | imagination, picture_organization | transformation→exploratory, color_richness→exploratory, line_combination→exploratory | 无参考图（明确配置） | clear | — |
| M9_J5 | full | 地图上的地方 | 题材 / 叙事；版本 ['full'] | imagination, picture_organization | transformation→exploratory, color_richness→exploratory, line_combination→exploratory | 无参考图（明确配置） | clear | — |

### OB → BP_OB

| task_id | 版本 | 题 | 相对锚定题改变了 | 九维关联（* = 可合理绕开） | 实例级降级（2026-10-11） | 材料 → 检查 | 状态 | 未决问题 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1_OB_01 |  | 两片叶子 | 锚定题 | realism, line_combination, picture_organization*, color_richness* | — | B1_OB_ref（always）→ 无法判断 | clear | — |
| B2_OB_01 |  | 苹果和两本书 | 材料；condition.age_max；condition.age_min；condition.band；题材 / 叙事 | realism, picture_organization, line_combination*, color_contrast* | — | B2_OB_ref（always）→ 不符合 | clear | — |
| B3_OB_01 |  | 桌上的四件物品 | 材料；condition.age_max；condition.age_min；condition.band；题材 / 叙事 | picture_organization, realism, line_combination*, color_contrast* | — | B3_OB_ref（always）→ 不符合 | clear | — |
| B4_OB_01 |  | 窗边静物 | 材料；condition.age_max；condition.age_min；condition.band；题材 / 叙事 | picture_organization, realism, line_combination*, color_contrast* | — | B4_OB_ref（always）→ 不符合 | clear | — |
| B5_OB_01 |  | 街角 | 材料；condition.age_max；condition.age_min；condition.band；题材 / 叙事 | picture_organization, realism, line_combination*, color_contrast* | — | B5_OB_ref（always）→ 不符合 | clear | — |
| B6_OB_01 |  | 客厅 | 材料；condition.age_max；condition.age_min；condition.band；题材 / 叙事 | realism, picture_organization, line_combination*, color_richness* | — | B6_OB_ref（always）→ 不符合 | clear | — |

### ST → BP_ST

| task_id | 版本 | 题 | 相对锚定题改变了 | 九维关联（* = 可合理绕开） | 实例级降级（2026-10-11） | 材料 → 检查 | 状态 | 未决问题 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1_ST_01 |  | 一起玩 | 锚定题 | picture_organization, imagination*, line_combination*, color_contrast* | — | 无参考图（明确配置） | clear | — |
| B2_ST_01 |  | 放学以后 | condition.age_max；condition.age_min；condition.band；题材 / 叙事 | picture_organization, imagination*, line_combination*, color_contrast* | — | 无参考图（明确配置） | clear | — |
| B3_ST_01 |  | 一件意外的事 | condition.age_max；condition.age_min；condition.band；题材 / 叙事 | picture_organization, imagination*, deformation*, color_contrast* | — | 无参考图（明确配置） | clear | — |
| B4_ST_01 |  | 同一个地方的两种感觉 | condition.age_max；condition.age_min；condition.band；题材 / 叙事 | picture_organization, transformation, color_contrast*, line_combination* | — | 无参考图（明确配置） | clear | — |
| B5_ST_01 |  | 距离 | condition.age_max；condition.age_min；condition.band；题材 / 叙事 | transformation, picture_organization, imagination*, color_contrast* | — | 无参考图（明确配置） | clear | — |
| B6_ST_01 |  | 地图上的地方 | condition.age_max；condition.age_min；condition.band；题材 / 叙事 | imagination, picture_organization, transformation*, color_contrast* | — | 无参考图（明确配置） | clear | — |

### FG → BP_FG

| task_id | 版本 | 题 | 相对锚定题改变了 | 九维关联（* = 可合理绕开） | 实例级降级（2026-10-11） | 材料 → 检查 | 状态 | 未决问题 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1_FG_01 |  | 一条线变什么 | 锚定题 | imagination, deformation*, picture_organization* | — | B1_FG_ref（always）→ 无法判断 | clear | — |
| B2_FG_01 |  | 两段线条的故事 | 材料；condition.age_max；condition.age_min；condition.band；题材 / 叙事 | imagination, picture_organization, deformation*, line_texture* | — | B2_FG_ref（always）→ 无法判断 | clear | — |
| B3_FG_01 |  | 线条里的地方 | 材料；condition.age_max；condition.age_min；condition.band；题材 / 叙事 | imagination, picture_organization, deformation*, color_richness* | — | B3_FG_ref（always）→ 无法判断 | clear | — |
| B4_FG_01 |  | 线条变角色 | 材料；condition.age_max；condition.age_min；condition.band；题材 / 叙事 | imagination, picture_organization, deformation*, line_texture* | — | B4_FG_ref（always）→ 无法判断 | clear | — |
| B5_FG_01 |  | 看见连接 | 材料；condition.age_max；condition.age_min；condition.band；题材 / 叙事 | transformation, imagination, picture_organization, deformation*, color_richness* | — | B5_FG_ref（always）→ 无法判断 | clear | — |
| B6_FG_01 |  | 壁画的碎片 | 材料；condition.age_max；condition.age_min；condition.band；题材 / 叙事 | imagination, transformation, picture_organization*, deformation* | — | B6_FG_ref（always）→ 无法判断 | clear | — |

### TR → BP_TR

| task_id | 版本 | 题 | 相对锚定题改变了 | 九维关联（* = 可合理绕开） | 实例级降级（2026-10-11） | 材料 → 检查 | 状态 | 未决问题 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1_TR_01 |  | 会帮忙的杯子 | 锚定题 | imagination, deformation, picture_organization*, color_richness* | — | B1_TR_ref（always）→ 不符合 | clear | — |
| B2_TR_01 |  | 雨伞的新本领 | 材料；condition.age_max；condition.age_min；condition.band；题材 / 叙事 | imagination, deformation, picture_organization*, color_richness* | — | B2_TR_ref（always）→ 不符合 | clear | — |
| B3_TR_01 |  | 茶壶救援机 | 材料；condition.age_max；condition.age_min；condition.band；题材 / 叙事 | imagination, deformation, picture_organization*, color_contrast* | — | B3_TR_ref（always）→ 不符合 | clear | — |
| B4_TR_01 |  | 自行车的新用途 | 材料；condition.age_max；condition.age_min；condition.band；题材 / 叙事 | imagination, deformation, picture_organization*, color_richness* | — | B4_TR_ref（always）→ 不符合 | clear | — |
| B5_TR_01 |  | 小空间台灯 | 材料；condition.age_max；condition.age_min；condition.band；题材 / 叙事 | imagination, deformation, picture_organization*, line_combination* | — | B5_TR_ref（always）→ 不符合 | clear | — |
| B6_TR_01 |  | 鞋子变生物 | 材料；condition.age_max；condition.age_min；condition.band；题材 / 叙事 | deformation, transformation, imagination*, picture_organization* | — | B6_TR_ref（always）→ 不符合 | clear | — |

### DS → BP_DS

| task_id | 版本 | 题 | 相对锚定题改变了 | 九维关联（* = 可合理绕开） | 实例级降级（2026-10-11） | 材料 → 检查 | 状态 | 未决问题 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1_DS_01 |  | 玩具箱标志 | 锚定题 | picture_organization, imagination*, color_contrast* | — | 无参考图（明确配置） | clear | — |
| B2_DS_01 |  | 图书角标志 | condition.age_max；condition.age_min；condition.band；题材 / 叙事 | picture_organization, imagination*, color_contrast* | — | 无参考图（明确配置） | clear | — |
| B3_DS_01 |  | 运动会吉祥物 | condition.age_max；condition.age_min；condition.band；题材 / 叙事 | imagination, picture_organization, deformation*, color_contrast* | — | 无参考图（明确配置） | clear | — |
| B4_DS_01 |  | 校园活动海报 | condition.age_max；condition.age_min；condition.band；题材 / 叙事 | picture_organization, imagination*, color_contrast*, transformation* | — | 无参考图（明确配置） | clear | — |
| B5_DS_01 |  | 校园少浪费 | condition.age_max；condition.age_min；condition.band；题材 / 叙事 | picture_organization, transformation, imagination*, color_contrast* | — | 无参考图（明确配置） | clear | — |
| B6_DS_01 |  | 我的画廊标志 | condition.age_max；condition.age_min；condition.band；题材 / 叙事 | picture_organization, imagination*, color_contrast* | — | 无参考图（明确配置） | clear | — |


## 3.x 草案（2026-10-11 先补的两类；**没有进库**，没有 task_id 和评分契约）

**BP_D1 · 为校园里一个明确用途设计一个标志（草案）** — 在校园情境中，为一个明确用途设计一个图形标志，让看到的人知道这里 / 这件事是什么；操作 purposeful_design；来源：为班级或学校的活动设计标识、请柬、贺卡、图表、海报（原文明确规定，kb:p56:t3-visual-design）；利用画笔或计算机为自己 / 同学做小设计（名片、席卡）（原文明确规定，kb:p52:t5-design）；识别公共场所的标识，了解其用途和所传递的信息（原文明确规定，kb:p49:t1-signs）；数字画布 + 只提交一份设计（基于来源改编，kb:p56:t3-visual-design）；具体场所（图书角 / 运动用品区）由项目给定（项目新增条件）

**BP_D2 · 看着一样自然的东西，把它的形状、颜色和纹理画下来（草案）** — 观察一个自然对象的形状、颜色与纹理并表现出来（和 M1/M2 的人造场景拉开）；操作 observe_represent；来源：观赏自然环境中的山水、树木、花草、动物，感知其形状美、色彩美和肌理美（原文明确规定，kb:p49:t1-nature）；临摹是被承认的模仿手法（原文明确规定，kb:p58:copy-vs-change）；观察对象改为一张特写参考图而不是实物（基于来源改编，kb:p49:t1-nature）；一张图只放一个对象、无背景干扰（项目新增条件）

| 草案 id | 蓝图 | 题 | 文案 | 材料 | 九维关联 | 状态 | 未决问题 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D1_A1 | BP_D1 | 图书角标志 | 为班级图书角设计一个标志，让同学看到它就想到这里可以阅读。图形和颜色由你决定。 | 无参考图（明确配置） | picture_organization(primary), imagination(secondary) | clear | — |
| D1_A2 | BP_D1 | 运动用品区标志 | 为学校的运动用品区设计一个标志，让同学看到它就知道这里放的是运动用的东西。图形和颜色由你决定。 | 无参考图（明确配置） | picture_organization(primary), imagination(secondary) | clear | — |
| D2_A1 | BP_D2 | 一片叶子 | 照着图，把这片叶子画下来：它的形状、颜色，还有叶脉的纹路。 | d2_nature_a（待制作） | realism(primary), line_texture(primary), color_richness(secondary) | blocked | R5 参考图文件存在（d2_nature_a） |
| D2_A2 | BP_D2 | 一只贝壳 | 照着图，把这只贝壳画下来：它的形状、颜色，还有表面的纹路。 | d2_nature_b（待制作） | realism(primary), line_texture(primary), color_richness(secondary) | blocked | R5 参考图文件存在（d2_nature_b） |

## 4. 材料检查（按依赖；没有视觉模型时需要看图的项是「无法判断」，裁出的显示帧在 `frames/`）

| 材料 | 用途 | 呈现类型 | 量到的 | 结论 | 不符合的项 | 视觉项 |
| --- | --- | --- | --- | --- | --- | --- |
| m1_scene_e | 正式观察参考（M1） | 扁平插画 | sat=0.311 fill_h=1.0 | 无法判断 | — | 7 项待看图 / 10 项被前提阻塞 |
| m1_scene_c | 正式观察参考（M1） | 扁平插画 | sat=0.52 fill_h=1.0 | 无法判断 | — | 7 项待看图 / 11 项被前提阻塞 |
| m1_scene_b | 正式观察参考（M1） | 扁平插画 | sat=0.474 fill_h=1.0 | 无法判断 | — | 7 项待看图 / 11 项被前提阻塞 |
| m1_scene_a | 正式观察参考（M1：整幅重现） | 扁平插画 | sat=0.451 fill_h=1.0 | 无法判断 | — | 7 项待看图 / 13 项被前提阻塞 |
| m1_scene_d | 正式观察参考（M1） | 扁平插画 | sat=0.45 fill_h=1.0 | 无法判断 | — | 6 项待看图 / 10 项被前提阻塞 |
| m2_scene_a | 正式观察参考（M2：大小 / 前后 / 遮挡） | 扁平插画 | sat=0.408 fill_h=1.0 | 无法判断 | — | 4 项待看图 / 11 项被前提阻塞 |
| m2_scene_b | 正式观察参考（M2） | 扁平插画 | sat=0.401 fill_h=1.0 | 无法判断 | — | 4 项待看图 / 10 项被前提阻塞 |
| m2_scene_d | 正式观察参考（M2） | 扁平插画 | sat=0.435 fill_h=1.0 | 无法判断 | — | 4 项待看图 / 10 项被前提阻塞 |
| m2_scene_c | 正式观察参考（M2） | 扁平插画 | sat=0.466 fill_h=1.0 | 无法判断 | — | 4 项待看图 / 10 项被前提阻塞 |
| m2_scene_e | 正式观察参考（M2） | 照片风（原图 1512×1040 放大到 2048×1408，比另四张略软） | sat=0.309 fill_h=1.0 | 无法判断 | — | 4 项待看图 / 10 项被前提阻塞 |
| m3_fragments_a | 印在初始画布上的碎片（M3） | 矢量（artquest/reconstruct.draw_stimulus 与 static/app.js:drawStimulus 同一实现） | 矢量 | 符合 | — | 0 项待看图 / 0 项被前提阻塞 |
| m3_fragments_b | 印在初始画布上的碎片（M3） | 矢量（artquest/reconstruct.draw_stimulus 与 static/app.js:drawStimulus 同一实现） | 矢量 | 符合 | — | 0 项待看图 / 0 项被前提阻塞 |
| m3_fragments_c | 印在初始画布上的碎片（M3） | 矢量（artquest/reconstruct.draw_stimulus 与 static/app.js:drawStimulus 同一实现） | 矢量 | 符合 | — | 0 项待看图 / 0 项被前提阻塞 |
| m3_fragments_d | 印在初始画布上的碎片（M3） | 矢量（artquest/reconstruct.draw_stimulus 与 static/app.js:drawStimulus 同一实现） | 矢量 | 符合 | — | 0 项待看图 / 0 项被前提阻塞 |
| m3_fragments_e | 印在初始画布上的碎片（M3） | 矢量（artquest/reconstruct.draw_stimulus 与 static/app.js:drawStimulus 同一实现） | 矢量 | 符合 | — | 0 项待看图 / 0 项被前提阻塞 |
| m4_umbrella | 供改造的物品参考（M4，on_demand） | 扁平插画 | sat=0.086 fill_h=0.659 | 无法判断 | — | 1 项待看图 / 6 项被前提阻塞 |
| m4_backpack | 供改造的物品参考（M4） | 扁平插画 | sat=0.114 fill_h=0.699 | 无法判断 | — | 1 项待看图 / 7 项被前提阻塞 |
| m4_chair | 供改造的物品参考（M4） | 扁平插画 | sat=0.059 fill_h=0.665 | 无法判断 | — | 1 项待看图 / 6 项被前提阻塞 |
| m4_teapot | 供改造的物品参考（M4） | 扁平插画 | sat=0.04 fill_h=0.597 | 无法判断 | — | 1 项待看图 / 6 项被前提阻塞 |
| m4_clock | 供改造的物品参考（M4） | 扁平插画 | sat=0.054 fill_h=0.659 | 无法判断 | — | 1 项待看图 / 6 项被前提阻塞 |
| m4_shoe | 供改造的物品参考（M4） | 扁平插画 | sat=0.063 fill_h=0.506 | 无法判断 | — | 1 项待看图 / 6 项被前提阻塞 |
| m4_bicycle | 供改造的物品参考（M4） | 照片级渲染（和另六张扁平插画不是一套） | sat=0.009 fill_h=0.915 | 不符合 | 非白像素占高 92%（规格 55%–90%；超出上限的在 2:1 缩略图里会被裁掉） | 1 项待看图 / 7 项被前提阻塞 |
| m6_scene_a | 供改色的中性场景（M6，always） | 扁平插画 | sat=0.164 fill_h=1.0 | 无法判断 | — | 4 项待看图 / 9 项被前提阻塞 |
| m6_scene_d | 供改色的中性场景（M6） | 扁平插画 | sat=0.309 fill_h=1.0 | 无法判断 | — | 2 项待看图 / 5 项被前提阻塞 |
| m6_scene_c | 供改色的中性场景（M6） | 扁平插画 | sat=0.412 fill_h=1.0 | 无法判断 | — | 2 项待看图 / 6 项被前提阻塞 |
| m6_scene_b | 供改色的中性场景（M6） | 扁平插画 | sat=0.487 fill_h=1.0 | 无法判断 | — | 2 项待看图 / 6 项被前提阻塞 |
| m6_scene_e | 供改色的中性场景（M6） | 扁平插画 | sat=0.358 fill_h=1.0 | 无法判断 | — | 4 项待看图 / 8 项被前提阻塞 |
| B1_OB_ref | 正式观察参考（首访 OB） | PNG 1600×1200（原样保留的旧素材） | sat=0.131 fill_h=0.552 | 无法判断 | — | 1 项待看图 / 5 项被前提阻塞 |
| B1_FG_ref | 片段参考（首访 FG：转抄到空白画布，不印在画布上） | PNG 1600×1200（原样保留的旧素材） | sat=0.0 fill_h=0.13 | 无法判断 | — | 1 项待看图 / 5 项被前提阻塞 |
| B1_TR_ref | 供改造的物品参考（首访 TR） | PNG 1600×1200（原样保留的旧素材） | sat=0.303 fill_h=1.0 | 不符合 | 306×342（规格 1600×1200） | 1 项待看图 / 5 项被前提阻塞 |
| B2_OB_ref | 正式观察参考（首访 OB） | PNG 1600×1200（原样保留的旧素材） | sat=0.288 fill_h=1.0 | 不符合 | 295×342（规格 1600×1200） | 1 项待看图 / 5 项被前提阻塞 |
| B2_FG_ref | 片段参考（首访 FG：转抄到空白画布，不印在画布上） | PNG 1600×1200（原样保留的旧素材） | sat=0.001 fill_h=0.297 | 无法判断 | — | 1 项待看图 / 5 项被前提阻塞 |
| B2_TR_ref | 供改造的物品参考（首访 TR） | PNG 1600×1200（原样保留的旧素材） | sat=0.312 fill_h=1.0 | 不符合 | 297×342（规格 1600×1200） | 1 项待看图 / 5 项被前提阻塞 |
| B3_OB_ref | 正式观察参考（首访 OB） | PNG 1600×1200（原样保留的旧素材） | sat=0.251 fill_h=1.0 | 不符合 | 297×342（规格 1600×1200） | 1 项待看图 / 5 项被前提阻塞 |
| B3_FG_ref | 片段参考（首访 FG：转抄到空白画布，不印在画布上） | PNG 1600×1200（原样保留的旧素材） | sat=0.001 fill_h=0.375 | 无法判断 | — | 1 项待看图 / 5 项被前提阻塞 |
| B3_TR_ref | 供改造的物品参考（首访 TR） | PNG 1600×1200（原样保留的旧素材） | sat=0.192 fill_h=1.0 | 不符合 | 308×342（规格 1600×1200） | 1 项待看图 / 5 项被前提阻塞 |
| B4_OB_ref | 正式观察参考（首访 OB） | PNG 1600×1200（原样保留的旧素材） | sat=0.127 fill_h=1.0 | 不符合 | 365×364（规格 1600×1200） | 1 项待看图 / 5 项被前提阻塞 |
| B4_FG_ref | 片段参考（首访 FG：转抄到空白画布，不印在画布上） | PNG 1600×1200（原样保留的旧素材） | sat=0.001 fill_h=0.443 | 无法判断 | — | 1 项待看图 / 5 项被前提阻塞 |
| B4_TR_ref | 供改造的物品参考（首访 TR） | PNG 1600×1200（原样保留的旧素材） | sat=0.099 fill_h=1.0 | 不符合 | 443×364（规格 1600×1200） | 1 项待看图 / 5 项被前提阻塞 |
| B5_OB_ref | 正式观察参考（首访 OB） | PNG 1600×1200（原样保留的旧素材） | sat=0.291 fill_h=1.0 | 不符合 | 342×364（规格 1600×1200） | 1 项待看图 / 5 项被前提阻塞 |
| B5_FG_ref | 片段参考（首访 FG：转抄到空白画布，不印在画布上） | PNG 1600×1200（原样保留的旧素材） | sat=0.001 fill_h=0.474 | 无法判断 | — | 1 项待看图 / 5 项被前提阻塞 |
| B5_TR_ref | 供改造的物品参考（首访 TR） | PNG 1600×1200（原样保留的旧素材） | sat=0.205 fill_h=1.0 | 不符合 | 357×364（规格 1600×1200） | 1 项待看图 / 5 项被前提阻塞 |
| B6_OB_ref | 正式观察参考（首访 OB）；第六段沿用本项目 M 族素材 | PNG 1600×1200（原样保留的旧素材） | sat=0.451 fill_h=1.0 | 不符合 | 2048×1408（规格 1600×1200） | 1 项待看图 / 5 项被前提阻塞 |
| B6_FG_ref | 片段参考（首访 FG：转抄到空白画布，不印在画布上）；第六段沿用本项目 M 族素材 | PNG 1600×1200（原样保留的旧素材） | sat=0.0 fill_h=0.573 | 无法判断 | — | 1 项待看图 / 5 项被前提阻塞 |
| B6_TR_ref | 供改造的物品参考（首访 TR）；第六段沿用本项目 M 族素材 | PNG 1600×1200（原样保留的旧素材） | sat=0.063 fill_h=0.506 | 不符合 | 2048×1408（规格 1600×1200） | 1 项待看图 / 5 项被前提阻塞 |
| d2_nature_a | 正式观察参考（D2：形状 / 颜色 / 纹理） | 照片或写实插画（和 M1/M2 不是一套也没关系：这是单对象特写） | 矢量 | 不符合 | 文件不存在（草案材料：待制作） | 0 项待看图 / 0 项被前提阻塞 |
| d2_nature_b | 正式观察参考（D2） | 照片或写实插画 | 矢量 | 不符合 | 文件不存在（草案材料：待制作） | 0 项待看图 / 0 项被前提阻塞 |

每份材料的问题清单（对象 → 可辨识 → 关系 → 显示帧）在 JSON 的 `materials[*].items` 里。


## 5. 提醒（不改变状态，分析时要记得）

| 检查 | 依据 | 怎么处理 | 首见家族 |
| --- | --- | --- | --- |
| R14 文案要求由工具保证 | 橡皮可用 | 无需改；分析时用 line_preservation 过程指标核实 | M7 |
