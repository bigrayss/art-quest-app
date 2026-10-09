# Post-use Structured Questionnaire v1.0（课后问卷）

2026-10-09 定稿，已做进 app：题目在 `artquest/post_use.py`，界面「我的 → 问卷」，记录存 `data/opinions/`（`instrument: post-use/1.0`），
研究员 `GET /api/v1/opinions` 连题目定义一起拿。英文在 `static/lang/en.js`。

定位：**literature-informed, system-specific post-use questionnaire**。不是标准量表，不合成总分。

## 研究问题

- **RQ1 System Experience** — How does the system support users' creative activities and interaction needs?
- **RQ2 Agent Interaction Preferences** — What levels of AI initiative, user control, and personalization do users prefer in an adaptive art-creation agent?

| 部分 | 内容 | 题数 |
|---|---|---|
| A. Current System Experience | 当前系统的实际使用体验 | 6 |
| B. Future Agent Preferences | 对未来 Agent 交互方式的偏好 | 3 |
| C. Open Feedback | 开放式改进意见 | 1 |

目标 5–8 分钟，预试确认；低龄儿童不能假定同样时间完成。

## Part A（五点同意度 + 「没用过 / 说不清」不计分）

1 非常不同意 · 2 不同意 · 3 一般 · 4 同意 · 5 非常同意。界面上只显示词，不显示数字。

| ID | 构念 | 题目 | 来源 |
|---|---|---|---|
| Q1 | Ease of Use | 我觉得这个 App 很容易使用。 | UMUX-LITE |
| Q2 | Perceived Usefulness | 这个 App 提供的功能能够满足我这次绘画的需要。 | UMUX-LITE |
| Q3 | Exploration | 这个 App 让我能够尝试不同的绘画方法和想法。 | CSI |
| Q4 | Expressiveness | 这个 App 能帮助我画出自己想表达的内容。 | CSI |
| Q5 | Creative Agency | 在创作过程中，我能够自己决定怎么画。 | 系统特定 |
| Q6 | Help Accessibility | 当我需要绘画帮助时，我能找到相应的功能或提示。 | 系统特定 |

这六题是面向本项目改写的条目：UMUX-LITE 原版是 7 点，CSI 有自己的完整题目和算分。不能称作标准 UMUX-LITE / CSI，不能算 CSI 总分。

## Part B

> 界面上的措辞（2026-10-09 用户定）：题干里不出现「以后 / 未来」，选项和陈述句末尾不加句号。下面是原始题面。

**Q7 Task Initiative（单选）** 如果以后 AI 可以自动生成绘画主题，你更希望怎样开始一幅新作品？
A 我自己决定画什么。 / B AI 推荐几个主题，由我选择。 / C AI 直接生成一个主题，但我可以更换。 / D AI 直接生成主题，我不需要再选择。 / E 不确定，要看具体情况。

**Q8 Proactive Assistance（单选）** 如果未来 AI 可以在绘画过程中主动提供建议，你更希望它怎样做？
A 只有我主动请求时，AI 才提供建议。 / B AI 可以显示一个小提示，由我决定是否查看。 / C AI 可以直接显示建议。 / D 要看当时的情况。

**Q9 Personalization Preferences（多选，F、G 与其他互斥）** 如果未来 AI 能根据你之前的绘画记录提供帮助，你希望它参考哪些信息？
A 我以前画过什么。 / B 我喜欢的绘画主题或风格。 / C 我以前遇到过哪些绘画困难。 / D 我完成过哪些绘画任务，以及完成情况。 / E 我以前接受或忽略过哪些 AI 建议。 / F 我不希望 AI 参考以前的记录。 / G 不确定。

用户希望使用某类信息 ≠ 该信息有预测价值；问卷选择 ≠ 授权收集。

## Part C

**Q10 System Improvement（开放）** 如果只能改进这个 App 的一个地方，你最希望修改什么？为什么？ 文字或口头（口头由老师记录）。

## 结果怎么报

- Part A：每题分布 / 均值或中位数，结合使用日志解释；**不合成总分**。
- Part B：各选项人数与比例；样本 8–12 人以描述为主，不做显著性检验；保留「取决于情况」「不确定」。
- 完整问卷进附录，正文留构念、依据、主要结果。

## Methods 段

> **Post-use Questionnaire.** Following the drawing activity, participants completed a short structured questionnaire assessing their experience with the current system and their preferences for future adaptive agent interactions. The questionnaire included six experience-related items informed by UMUX-LITE, the Creativity Support Index, and system-specific design goals, three questions examining preferences for agent initiative and personalization, and one open-ended improvement question. Responses to system-specific items were analyzed descriptively rather than treated as a validated composite scale.

正式用前：按年龄调整措辞并做认知预试，不同版本在分析时分开；论文透明报告题目来源、修改和测量限制。

## 文献

- Lewis, J. R., Utesch, B. S., & Maher, D. E. (2013). UMUX-LITE: When there's no time for the SUS. *CHI '13*. https://doi.org/10.1145/2470654.2481287
- Cherry, E., & Latulipe, C. (2014). Quantifying the Creativity Support of Digital Tools through the Creativity Support Index. *ACM TOCHI, 21*(4). https://doi.org/10.1145/2617588
- HarmonyCut (CHI 2025). https://doi.org/10.1145/3706598.3714159
- Good Fences Make Good Learning (CHI 2026). https://doi.org/10.1145/3772318.3791657
- Exploring the Role of Interaction Data to Empower End-User Decision-Making in UI Personalization (CHI 2026). https://doi.org/10.1145/3772318.3791022
- When Should Users Check? (CHI 2026). https://doi.org/10.1145/3772318.3790655
- Mellor, D., & Moore, K. A. (2014). The use of Likert scales with children. *J. Pediatric Psychology, 39*(3). https://pubmed.ncbi.nlm.nih.gov/24163438/
