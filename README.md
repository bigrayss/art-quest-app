# ArtQuest — AI 美术教育游戏 App（Stage 1 · PC 核心原型）

按照 `docs/AI美术教育游戏App_分阶段开发与教育系统指南_v0.2.docx` 的 Stage 1 目标实现的最小闭环：

> 任务 → 表达意图 → 自由绘画 → 过程截图 → KidsArtBench 9 维评分 → AI 文字反馈 → 自己修改一次 → 保存 Before / After

没有 API key 也能完整跑通（离线启发式评分 + 模板反馈）；设置 `ANTHROPIC_API_KEY` 后自动切换为 Claude 视觉评分与 AI 教练反馈。

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env          # 可选：填入 ANTHROPIC_API_KEY
./run.sh                      # 默认 http://127.0.0.1:8000
```

在 HPC / 远程服务器上运行时，本机执行 `ssh -L 8000:127.0.0.1:8000 <server>` 后打开浏览器访问 `http://127.0.0.1:8000`。

测试：

```bash
./test.sh                     # 72 项，离线后端，不需要 API key
```

其中 `tests/test_browser.py` 会用系统的 Chrome 真跑一遍（缩放后坐标是否还准、含撤销的 session 能否重建）。
没装 Playwright 或没有 Chrome 就自动跳过：

```bash
.venv/bin/pip install playwright   # 用系统 Chrome，不必 playwright install
```

## 已实现（对应指南 §02 / §08 开发顺序）

| # | 指南要求 | 实现 |
|---|---|---|
| 1 | PC 画布 + 3–4 种基础工具 | 铅笔 / 笔刷（支持数位板压感）/ 马克笔（半透明）/ 橡皮，调色盘 + 自定义颜色，粗细，Undo / Redo（Ctrl+Z / Ctrl+Y），清空，**缩放 / 平移**（滚轮、`+` `-` `0`、空格或中键拖动、✋ 移动） |
| 2 | 保存最终作品 | 服务器保存 `before.png` / `after.png`；也可下载到本机 |
| 3 | 记录创作过程 | **笔触级 stroke log（含 pressure / tilt）+ 统一 event log 为主数据**；每 45 s（`ARTQUEST_SNAPSHOT_INTERVAL`）一张画布快照作辅助 |
| 4 | 3–5 个 Creative Quest | 5 个：情绪表达、想象、Transformation、Color/Composition、Story（`artquest/quests.py`） |
| 5 | Intent 输入 | 画前情绪（chips）+ 一句话意图 |
| 6 | KidsArtBench 9 维评分 | 可插拔接口 `artquest/scoring/`：`claude`（结构化 JSON 输出）/ `heuristic`（离线） |
| 7 | AI 文字反馈 | `artquest/feedback/`：三段式「我看到 / 一个问题 / 可以试试」，遵守“帮助思考、不替代创作、不给标准答案、不提分数”的原则 |
| 8 | 修改并保存 Before / After | 反馈后可修改一次（或跳过），再次评分 + 前后对比评语，展示 9 维差值 |
| 9 | 找少量用户跑 session | 首页「作品记录」可浏览所有 session，直接打开图片与 JSON |

**明确不做**（指南 Stage 1 排除项）：图层、大量笔刷、协作、社交、积分、iOS/Android、本地模型、云端、教师/家长后台。

## 数据结构（schema 3 · 四个数据文件）

**stroke / event log 是主数据，截图只是辅助。** 一次创作一个目录（`data/` 已 gitignore，
儿童作品不要提交）：

```
data/dataset.json               数据集清单：schema、版本、各项计数（导出时刷新）
data/sessions/<session_id>/
  session.json        一次任务里所有「小体量、非时间序列」的东西：身份、**冻结的任务定义**、
                      条件、设备、画布、时间、个性化、自评、QC
  strokes.jsonl.gz    画本身，一行一笔
  events.jsonl.gz     所有非绘画操作——**反馈也在这条线上**，它本来就是过程中的一个事件
  labels.jsonl        人写下来的 ground truth：教师评分 + 专家过程标注
  final.png           最后交上来的作品
  checkpoints/        只留真的需要的关键帧：`before_feedback.png`（有修改才有）
  reference/          孩子当时看到的那张刺激图的副本（static/refs 里的会被替换）
```

一条原则决定了什么进哪里：

> **凡是不高频、不是时间序列的，都进 `session.json`。**
> **凡是能算出来的，都不存。**

`metadata.json` / `condition.json` / `self_report.json` / `personalization.json` /
`quality.json` 合并成了 `session.json`；`feedback.jsonl` 并进事件流；
`ratings.jsonl` + `annotations.jsonl` 合并成 `labels.jsonl`（用 `type` 区分）。
一个 session 从十几个文件收敛到**四个数据文件 + 一张图**。

**旧数据一个字节都不动。** schema 1 / 2 的 session 保持原样，
`artquest/storage.py` 里的读取方把它们折到当前形状——和 `events.canonical()`
折叠旧事件名是同一个契约，`tests/test_research.py` 有一条专门守它的测试。

### 一条 stroke

```json
{"seq":12,"stroke_id":"s00012","phase":"before","op":"draw","tool":"brush","color":"#e63946",
 "size":6,"opacity":0.9,"pointer":"pen","pressure_supported":true,"tilt_supported":true,
 "zoom":4.0,"t0_ms":48210,
 "points":[[368.3,256.2,0,0.31,12,-4],[369.2,257.1,16.7,0.34,12,-4]]}
```

$$Raw\ Stroke = Geometry + Time + Tool\ State$$

point 的六个槽位固定是 `[x, y, dt_ms, pressure, tilt_x, tilt_y]`，画布像素坐标，
`dt_ms` 从这一笔的 `t0_ms` 起算。绝对时间随时可以还原：

$$t_{point} = \text{started\_at} + t0_{stroke} + dt$$

所以**每条记录都不带自己的时钟**——没有 `t_end_ms`（= `t0_ms` + 最后一个 `dt`）、
没有 `ts`。速度、曲率、笔长、bounding box 一律留给离线分析。

有两个字段看着像能算出来，但留着是有理由的：

| 字段 | 为什么不能算 |
| --- | --- |
| `zoom` | 画这一笔时孩子**看到的**画面。坐标里没有它（缩放是视图变换，见下），而「什么时候放大去抠细节」本身就是过程信号 |
| `pressure_supported` / `tilt_supported` | 说明 `null` 是「**没有这个传感器**」而不是「传感器读到了空」。只看点是分不出来的 |

`pointermove` 走 `getCoalescedEvents()`，数位板可拿到完整输入率（可达 ~240 Hz）。

**没测到的通道存 `null`，不伪造。** 鼠标恒定返回 `pressure = 0.5` 且没有 tilt——把它当读数
记下来，鼠标画的每一笔的每一个点都会带上一个编造的数字，离线分析分不出它和真实读数的区别。
渲染器仍然需要一个宽度，就退回中性的 0.5——**日志保持诚实，图像不假装这个退化值是读数**；
导出的 `mean_pressure` 只对真正测到的点求均值，全没测到就留空。

**缩放不进坐标。** 缩放 / 平移是画布元素上的一个 CSS transform，绘图上下文完全不知情；指针坐标经
`getBoundingClientRect()` 换算，而它返回的正是变换后的盒子——所以 8 倍放大下画的笔，和 100% 下画的笔
落在同一个坐标系里，replay、undo、快照全都不受影响。这条不变式由 `tests/test_browser.py`
在真实 Chrome 里验证。

### 图片：能重建的就不存

$$Artwork(t) = Replay(Strokes_{0:t},\ Events_{0:t})$$

所以默认**只存 `final.png`**。定时截图默认关掉（`ARTQUEST_SNAPSHOT_INTERVAL=0`）——
它只是日志已经包含的东西的一份副本。唯一另外留的是 `checkpoints/before_feedback.png`，
而且只有真的走了修改关才写：那一帧是**实验节点**，replay 看不出它特殊在哪。
（合并前，一个没修改过的 session 会把同一张 PNG 存三份。）

### 压缩：跑完就压

session 通过 QC（`lifecycle = server_verified`）时，两条过程流就地压成
`strokes.jsonl.gz` / `events.jsonl.gz`——现有真实日志 409 KB → 50 KB，**省 88%**。
读是透明的，迟到的一批数据会先解冻再追加，调用方不需要知道这件事。
`labels.jsonl` 不压：教师可能几周后才评分。

### 派生数据不跟着 session 存

`features.json` / `embedding.json` / `statistics.json` 这类东西一个都不写进 session 目录——
它们可以重算，重算才能让改进后的算法回溯地作用到每一条旧数据上。统一由
`tools/export_dataset.py` 在 dataset 层生成。

### 统一事件时间轴（`artquest/events.py` 是唯一权威）

**一条时间轴，一个时钟。** `t_ms` 就是那个时间戳——从开始画算起的毫秒；墙钟时间由
`metadata.times.started_at_ms + t_ms` 还原，所以没有任何事件自带墙钟，也就没有两个模块
对"现在几点"产生分歧的余地。服务端事件（反馈展示、会话结束）用引发它的那次请求里的客户端时钟，
落进同一条流。

```
SESSION_START  TASK_SHOW  CANVAS_GEOMETRY  TASK_SUBMIT  SESSION_END
STROKE_START  STROKE_END  ERASE  UNDO  REDO  CLEAR
BRUSH_CHANGE  COLOR_CHANGE  SIZE_CHANGE  ZOOM  PAN
REFERENCE_SHOW  REFERENCE_OPEN  REFERENCE_CLOSE  REFERENCE_ZOOM  REFERENCE_PAN
REFERENCE_FOCUS  CANVAS_FOCUS
PAUSE_START  PAUSE_END  TIME_LIMIT_REACHED
FEEDBACK_SHOW  FEEDBACK_DISMISS  REVISION_START  REVISION_SKIPPED
HISTORY_SHOWN  RATING_ADDED  QUESTIONNAIRE_SUBMITTED  DOWNLOAD
```

`STROKE_START` 在落笔时记，不等抬笔——planning latency 和 first-stroke region 问的是
孩子**什么时候开始**，不是什么时候松手。`FEEDBACK_SHOW` 就是反馈本身（正文、来源、
`target_region` 都在它的 payload 里），既是「反馈前 / 反馈后」的锚点，也省掉了
一条事件 + 一个文件写同一件事；`FEEDBACK_DISMISS` 带 `read_ms`，反馈被看了多久本身是信号。
读的时候 `storage.session_feedback()` 会把它摊回反馈那个形状，所以
`stroke / undo / feedback / pause / stroke` 按时间排一遍就能读。

统一词表时有几个名字变了。直接改名会让已经采到的 session 变成孤儿，所以
`events.canonical()` 把旧名折叠到新名，**所有读取方都走它**——旧日志一个字节不动，
读取方不再需要关心：

| 旧名 | 现名 |
|---|---|
| `STROKE` | `STROKE_END` |
| `IDLE_START` / `IDLE_END` | `PAUSE_START` / `PAUSE_END` |
| `FEEDBACK_SHOWN` | `FEEDBACK_SHOW` |

`events.unknown_types()` 能查出"某个模块自己发明了一个名字"。

`ZOOM` / `PAN` **一次手势一条记录**（和一笔 stroke 同构：原始轨迹放在记录里面，而不是刷屏成几百行）：

```json
{"seq": 41, "t_ms": 31200, "type": "ZOOM",
 "payload": {"from": 1, "to": 4.3, "source": "wheel", "at": [-1820, -1290], "dur_ms": 534,
             "steps": [[0, 1.2], [31, 1.44], ...]}}
```

`source` 区分 `wheel` / `button` / `key`；`PAN` 的 payload 是 `{from, to, zoom, dur_ms, points}`。
一次缩放手势会在它所服务的那一笔开始之前结账，所以时间线上 `ZOOM` 永远排在对应 `STROKE` 前面。

`STROKE` / `ERASE` 带 `stroke_id`，把事件流和笔画流对起来；**`UNDO` / `REDO` / `CLEAR` 带
`{removed, restored, visible_n}`**，说明这一步把哪几笔拿下了画布、又把哪几笔放了回去：

```json
{"seq": 87, "t_ms": 52140, "type": "UNDO", "payload": {"removed": ["s00012"], "restored": [], "visible_n": 11}}
```

没有这个 payload，一段含撤销的日志是**无法回放**的——笔画流是 append-only 的，被撤销的笔永远留在
`strokes.jsonl` 里，只有事件流知道它最后不在画上。撤销掉的笔本身也是过程信号（`strokes_removed`），
所以只标记、不删除。

### 先本地保存，再上传

前端先把每一笔写进 IndexedDB，再分批 flush 到 `/api/sessions/{id}/log`。断网、关标签页、刷新都不丢：
队列跨会话保留，重连后自动补传；每条记录带流内单调 `seq`，服务器丢弃 `seq` 不大于水位线的重复记录，
**重发不会写重**。被服务器拒绝（4xx）的记录会逐条重试并隔离保留，不会堵住后面排队的数据。

### 数据质量检查

session 结束时自动跑 `artquest/qc.py`，结果写进 `metadata.json.qc`：任务是否已知、事件/笔画是否为空、
final 图是否落盘、时间是否单调、时长是否合理、每笔采样点是否够 replay、本地队列是否清空，外加两项
**日志与作品是否自洽**的检查：

| 检查 | 判据 | 说明 |
|---|---|---|
| `log_streams_agree` | 精确，无阈值 | 事件流画过的每一笔都要在 `strokes.jsonl` 里，反之亦然；undo/redo/clear 引用的 id 必须真的画过。丢批次、id 重复、悬空引用都会以 id 列表的形式报出来。**这项是真正可信的把关。** |
| `replay_matches_final` | `rel ≤ 0.30`（可用 `ARTQUEST_MAX_REPLAY_DIFF` 调） | 从日志重建的画和 `final.png` 的**含墨量差异**（96 px 灰度下 1−IoU）。用 `data/` 里浏览器真实画出的 session 标定：**正确**的重建也有 0.11–0.13 的底噪，因为 PIL 的线比 canvas 细（墨量约为作品的 78 %）。所以它只是粗筛——空白重建、画布尺寸错、整批笔画丢失能抓到，多画两笔抓不到。 |

**只标记，不删数据。**

## 评分与反馈后端

| 环境变量 | 取值 | 说明 |
|---|---|---|
| `ARTQUEST_SCORER` | `auto` / `claude` / `heuristic` | auto：有 key 用 claude |
| `ARTQUEST_FEEDBACK` | `auto` / `claude` / `template` | 同上 |
| `ARTQUEST_MODEL` | 默认 `claude-opus-5` | |
| `ARTQUEST_EFFORT` | 默认 `medium` | Opus 5 自适应思考，effort 控制深度 |

接入正式 KidsArtBench 模型：在 `artquest/scoring/` 新增一个实现 `Scorer` 协议的类（输入 PNG bytes + quest + intent，输出 9 维分数与说明），并在 `get_scorer()` 中注册。9 维定义见 `artquest/scoring/base.py`（当前 1–5 分，`SCALE_MAX`，可按官方量表调整）。

`heuristic` 后端只对色彩 / 线条 / 画面组织有信号，写实、变形、想象、转化四个语义维度返回中间值并标注“需模型评分”。

## Creative Mission Task Library：任务是一个「测量对象」

最关键的设计变化：**任务不再只是给孩子看的一段 prompt**。库里的每一行同时知道六件事——
它想诱发什么行为、对应哪些 9D 属性、**哪些维度它根本无法考察**、属于哪个 parallel form、
在什么条件下执行、孩子看到的是哪种叙事。

后台是 experimental condition，孩子看到的是 **Creative Mission**。孩子不该觉得
"现在在测你的 imagination"，而该觉得"我要解决一个有趣的问题"——所以每个家族都有叙事化的 prompt bank。

| 家族 | 孩子看到 | 研究目标 | Primary 9D |
|---|---|---|---|
| M0 自由创作 | 自己决定画什么 | 开放创作基线（每个研究字段取宽松值） | 无（全部 exploratory） |
| M1 博物馆修复师 | 修复一幅损坏的画 | visual organization、global/local strategy、reference-based reconstruction | Realism · Picture Org · Line Comb |
| M2 探险家速写 | 准确记录一个场景 | observation + spatial reasoning + reference strategy | Realism · Picture Org |
| M3 失落的碎片 | 把碎片变成一整幅画 | incomplete-figure creativity（TCT-DP / TTCT 范式，刺激自制） | Imagination · Transformation · Picture Org |
| M4 变异物体实验室 | 把普通物体改造成别的用途 | deformation + transformation + imagination | Deformation · Transformation · Imagination |
| M5 融合发明家 | 融合两个不相干的概念 | conceptual integration（与 M4 是不同 construct） | Transformation · Deformation · Imagination |
| M6 情绪世界 | 用颜色换一种感觉 | 让 color richness / contrast 真正 observable | Color Richness · Color Contrast |
| M7 线条冒险 | 先只画线，再长成作品 | line combination / texture，两阶段 | Line Comb · Line Texture · Transformation · Imagination |
| M8 不可能世界 | 规则不同的世界里的生活 | 最接近 authentic creation，但由 world-rule generator 约束 | Imagination · Transformation · Picture Org |
| M9 故事挑战 | 一个故事的开头 | ecological validity：受控任务里的模式在真实创作里还在吗 | Imagination · Picture Org |

**parallel form 与生成器**：M4 由 `base object × environment × function` 三张卡组合，
每个组合再配 `minimal / story / challenge` 三种 prompt style（style 是被记录的变量，不是随手写法）；
M5 是概念对，M7 是抽象概念，M8 抽 2–3 条 world rule。当前库共 **75 个 form**。

**task_id 是后面每张表的外键**，所以稳定、自解释、纯 ASCII：

```
M4_UMB_UW_TRA_story     M4 · 雨伞 · 海底 · 交通工具 · story 叙事
M3_C                    M3 · 第 C 个 prompt
M6_A_dangerous          M6 · 情绪开关 · dangerous
```

原来 5 个开放任务作为 **M0** 家族原样保留（id 不变）——已经采到的 session 必须继续可解释。

孩子在藏宝图上看到的是 **10 个家族**，不是 75 张卡；具体 form 由 protocol 分配（Study Mode）
或随机（自由玩）——"拿到哪个 parallel form"不是孩子该做的选择。

### Rubric Contract：N/A ≠ 低分

每个任务对九个维度逐一声明角色，而不是简单存一个 `target_dimensions`：

| 角色 | 含义 |
|---|---|
| `primary` | 任务就是为诱发它而建的，是这个任务真正测的东西 |
| `secondary` | 这里能稳定观察到，但不是任务的目的 |
| `exploratory` | 收了，但没有强先验：看，别下结论。**任务没提到的维度自动归这里** |
| `not_applicable` | 任务根本无法诱发它，**必须给出理由** |

> **N/A 不是低分。**

M1 只给铅笔，画面里不会出现颜色选择。把「色彩丰富」记成 1 分，是在说"这孩子用色很差"——
一个这个任务从没测过的论断；而这个 1 会平均进他的能力画像、进模型的训练数据、进跨任务比较。
所以类型层面强制：

- N/A 维度的分数是 `None` 加一句理由，**后端就算评了也会被抹掉**（`rubric.apply_contract`）；
- Claude 评分器**只被问可评维度**（强迫回答和真实低分无法区分）；
- 教师给 N/A 维度打分会被 **422 拒绝**；
- 前端玫瑰图上 N/A 是**虚线空槽 + 灰色标签**，不是一片短花瓣。

沉默不等于 N/A：任务没提到的维度归 exploratory，否则手滑漏掉一个维度就等于悄悄不测了。
未知维度、一个维度身兼两角、N/A 没写理由——三者都会让任务**在加载时被拒绝**，
而不是产生一批事后没人能解释的数据。

### 初始画布不一定是白的

M3 的碎片是**画布空间里的矢量图元**（不是位图），`artquest/reconstruct.py:draw_stimulus` 与
`static/app.js:drawStimulus` 是同一套实现的两端。因为 replay 是
`初始画布 + stroke 流 + 事件`——两端画得不一样的话，每个碎片 session 都会栽在 `replay_matches_final` 上。
（实测浏览器与 PIL 的重建 `rel = 0.133`，正好是栅格化底噪。）

### 刺激图目前是占位图

`static/refs/` 下 19 张参考图是**生成的占位图**，上面明确写着 PLACEHOLDER。
`static/refs/manifest.json` 列出还没换成真图的 `stimulus_id`；QC 的 `stimulus_ready`
会把用了占位图的 session 标出来。**试点数据不是无效数据——标记，不阻拦。**
换上真图后把 id 从 manifest 里删掉即可。

## Protocol：75 个 form → 每个孩子一条短而平衡的路线

```json
{"protocol": {"protocol_id": "pilot1",
  "required_families": ["M1", "M3", "M4", "M6", "M9"],
  "anchor_task": "M1_A", "heldout_task": "M9_A",
  "randomization_rule": "latin", "prompt_style_rule": "balanced"}}
```

- 每个家族一个 slot，被试之间轮转拿到不同的 parallel form；
- `anchor_task` / `heldout_task` **取代**该家族的轮转位，而不是叠加上去（否则该家族被测两次、路线凭空多一站）；
- 拉丁方**只作用在自由位**上——把五个一起排完再把 anchor 强行拉到第一、heldout 拉到最后，
  会把刚算好的平衡毁掉（实测中间三位从 4/4/4 变成 6/2/4）；
- `prompt_style_rule: balanced` 让 prompt style 在被试间轮转，而不是和任务绑死。

**planned vs actual**：第一次算出的 `planned_order` 冻进名册；
`GET /api/participants/{pid}/protocol` 给出 planned / actual / `followed_plan` / `missing` /
`unplanned` / `repeats`。任务顺序是潜在混淆，要**事后可查**，不是假定。

## 任务系统 = 游戏关卡（一张表，两种读法）

孩子看到的「关卡」和研究者读到的「task」是同一行数据（`task_id == quest.id`）。开放创作任务取的是每个
研究字段的**宽松取值**（`reference: null` / `time_limit_sec: null` / `allowed_tools: null` = 全部工具）——
这是合法的条件取值，不是缺字段。约束更紧的题就是同一张表里字段更紧的几行，因此 user effect 与 task effect
天然可分，不需要第二套任务系统。

研究者不改代码就能加题：把一个 JSON 列表放到 `$ARTQUEST_DATA_DIR/tasks.json`，按 `task_id` 合并覆盖内置任务。
rubric 不合法的任务会被**拒绝加载**并记日志，其余任务照常工作。

```json
[{"id": "shape_basic", "type": "观察", "title": "照着画：三个基本形状",
  "prompt": "……", "category": "observation", "difficulty": 1,
  "time_limit_sec": 300, "allowed_tools": ["pencil", "eraser"],
  "reference": {"id": "shapes_a", "file": "/static/refs/shapes_a.png", "mode": "on_demand"},
  "focus_dims": ["realism", "line_texture"], "icon": "🔺", "color": "#2b7de8"}]
```

## 界面：手机优先的 app（形式参考多邻国）

界面按**一块屏幕做一件事**来分，底部四个 tab（桌面自动变成左侧导航栏），
做任务时导航整个收起来，只剩画画：

开场是**游戏式的三步**：先见到精灵和它身上的九个属性 → 进入世界 → 再挑任务。
属性不是分数，它长在「练过什么」上；没画过画的时候彩点是灰的，孩子用的颜色把它点亮
（`ui=quiet` 条件下整个开场不出现）。进过一次之后，这一会儿里再点「地图」就直接到关卡路径，
顶栏留一个彩点头像随时能回世界。

| tab | 这块屏幕负责什么 |
| --- | --- |
| **地图** | 门口是彩点的世界（精灵 + 九属性 + 成长条）；进去是竖着蜿蜒下去的关卡地图，一个任务家族一个大圆钮，走过的盖星，彩点站在你该去的下一关旁边 |
| **图鉴** | 自己的作品收藏 + 老师精选墙 |
| **彩点** | 九属性成长面板 + 徽章墙（把每次上报的徽章并起来，看还差哪几枚） |
| **我的** | 作品记录表、后端与本机代号 |

创作流程（心愿 → 创作 → 支招 → 进化 → 宝藏）是**盖在 tab 之上的一条流水线**：
顶栏变成「返回 + 一条细进度条 + 彩点 + 第几步」，不再占掉一整块地方。
条件里没有 AI 反馈时，支招和进化不会出现在进度里——不承诺走不到的站。

视觉规则：

| 规则 | 怎么做的 |
| --- | --- |
| **每个能按的东西都有厚度** | 按钮、卡片、关卡圆钮都有下沿，按下去 `translateY` 真的陷进去 |
| **扁平，但收着用** | 色相沿用多邻国那一套，饱和度和明度各降一档（主色橙 `#f79433`、完成绿 `#6cc24a`、次要蓝 `#4db8ef`）；一屏里只让一两块颜色说话，最亮的东西应该是孩子的画 |
| **世界与关卡是「捏出来的」** | claymorphism：一层外投影给体积，两层内投影把它吹鼓（世界卡片、属性格、关卡圆钮、进入按钮）。2026 年 iPad 上给小孩用的 app 主流就是这套软糖质感，而且它天生低饱和，跟上一条同向 |
| **iPad 当 app 用** | 装到主屏没有地址栏；一根手指画、两根手指看（捏合缩放 / 拖动平移 / 双指轻点撤销）；见过手写笔之后手指只做手势（防手掌误触）；触摸目标 ≥44pt；换屏是滑进来的（画画那屏除外，动画期间祖先的 transform 会让落笔坐标偏） |
| **圆润的粗体字** | 拉丁字母用自托管的 Nunito（`static/fonts/`，SIL OFL 1.1，可变字重一个文件），中文落 Noto Sans CJK |
| **不用 emoji** | 全部图标是 `app.js` 里的 `ICONS`（约 35 枚，24×24、2.2 粗描边、`currentColor`） |
| **十个任务家族各有一块颜色** | 家族色写在 `missions.py`，地图圆钮、图鉴、chip 都跟着它走 |

约束没有变：徽章只读过程，`ui=quiet` 依然把整套游戏化外观收起（`body.quiet`），
孩子面前不出现分数或排名。

## Study Mode

不是「关掉游戏」，而是**固定并记录**那些本来会悄悄变化的东西。任何 session（包括自由玩）都会把
`condition` 冻结进 `metadata.json`，所以游戏化程度是一个**被记录的变量**，可以控制、也可以当自变量研究。

| 条件字段 | 取值 | 作用 |
|---|---|---|
| `ui` | `full` / `quiet` | 游戏化程度（彩点、闯关路线、徽章、图鉴） |
| `reference_allowed` | bool | 是否允许看参考图（开关时间进 event log） |
| `undo_allowed` | bool | 是否允许撤销 |
| `zoom_allowed` | bool | 是否允许缩放 / 平移画布（关掉时工具条隐藏、滚轮与空格失效） |
| `history_mode` | `none` / `history` / `personalized` | 个性化臂：不看历史 / 看自己的历史 / 模型读表示 |
| `growth_display` | `none` / `badges` / `full` | 孩子能看到多少自己的成长（彩点九属性、徽章、玫瑰图） |
| `gallery_display` | `none` / `after_submit` / `always` | 能不能看到别人的作品，以及什么时候 |
| `share_consent` | bool | 这个孩子的作品是否获准展示给其他人。**默认 false，从不推断** |
| `questionnaire` | bool | 结束前是否做 1–5 自评 |
| `feedback_source` | `ai` / `teacher` / `none` | 反馈来源 |
| `time_limit_sec` | int / null | 时限，到点自动提交并记 `TIME_LIMIT_REACHED` |

**顺序随机化**：藏宝图上的关卡顺序就是 task sequence——按被试编号用**平衡拉丁方**排（每个任务在每个位置
出现次数相同），同一个编号永远复现同一顺序。孩子看到的是关卡，reviewer 看到的是 counterbalanced order。

配置放 `$ARTQUEST_DATA_DIR/study.json`（`groups` 可做被试间分组）：

```json
{"active": true, "study_id": "pilot1", "tasks": [], "order": "latin",
 "condition": {"ui": "quiet", "questionnaire": true, "undo_allowed": false},
 "groups": {"B": {"ui": "full"}}}
```

被试用 `http://127.0.0.1:8000/?study=1&pid=P007` 进入；代号存 localStorage，之后同一台设备自动带上。
名册（代号 → 序号，用于拉丁方轮转）在 `$ARTQUEST_DATA_DIR/participants.json`，**不含真名**。

身份是两个匿名 id 并存：设备自动生成的 `anon_id`（日常自由玩也能跨任务对齐）+ 研究员分配的
`participant_id`。

## Reference 交互：look → draw → check → correct

有参考图的任务，参考图自己也有视口——能缩放、能拖动。因为"看了多久、放大到多细、
注意力什么时候在两边之间来回"都是过程信号，而如果参考图只是一张扁平缩略图，这些**根本不存在**。

| 事件 | 记什么 |
|---|---|
| `REFERENCE_SHOW` | 任务把它**呈现**出来（与孩子主动打开是两回事），带 `placeholder` 标记 |
| `REFERENCE_OPEN` / `REFERENCE_CLOSE` | 孩子开/关；关闭时带 `view_duration_ms` 与 `viewed_total_ms` |
| `REFERENCE_ZOOM` / `REFERENCE_PAN` | 参考图自身的缩放与平移 |
| `REFERENCE_FOCUS` / `CANVAS_FOCUS` | 注意力在参考图与画布之间切换——`canvas_to_reference` / `reference_to_canvas` 两个计数由此得来 |

## Session 生命周期：对孩子完成 ≠ 对数据完成

```
recording → completed_local → pending_upload → uploaded → server_verified
```

`status` 说的是**孩子**走到哪了，`lifecycle` 说的是**数据**走到哪了。一幅画完了但最后一批
日志没上传成功，对孩子是完成，对数据不是。`server_verified` 只有在
`log_streams_agree` + `replay_matches_final` + `uploads_flushed` 三项都过时才会置上，
而且**只进不退**——一个迟到的重复批次不能把已验证的 session 降级。

`quality.json` 与数据并排存放；`log_checksum` 记下两条主日志的内容哈希，
以后的损坏或半截重传能被发现，而不是被静默分析。

## 反馈 → 修改：不只记下反馈，还要能回答"他改了吗、改在哪"

采集清单要求的是 `feedback content + timestamp + source + target region + subsequent revision`。
前四项是有人写下来的字段；**第五项不是字段**——它只作为"某条反馈"与"其后那些笔"之间的关系存在，
而且只有当区域和笔画在**同一个坐标系**里时才算得出来。

| 记录 | 在哪 |
|---|---|
| content / timestamp / source / type | `feedback.jsonl`，每条一个 `feedback_id` |
| target region | 同上，`target_region`，**画布像素坐标**（`rect` / `point` / `poly`） |
| shown at | `FEEDBACK_SHOWN` 事件，切分「反馈前 / 反馈后」的锚点 |
| subsequent revision | `REVISION_START` / `REVISION_SKIPPED` 带 `feedback_id` + `latency_ms` |
| 关系本身 | `GET /api/sessions/{id}/revision`（`artquest/revision.py`，现算不落库） |

`target_region` 是**受约束的类型**，不是自由字典：小于 2px 的矩形会被拒，因为那不是"很小的区域"，
而是**没换算的归一化坐标**——这个字段最容易被这样误用，而一旦写进去，所有分析都会静默地得到
一个没有任何笔能落进去的区域。

### 归因给出什么

值得要的数不是"他之后画了没有"（流程本来就请他改），而是**他有没有比之前更多地在反馈指向的地方动笔**。
所以每条反馈配两个窗口——显示之前的全部，和显示之后到下一条反馈之间——以及各自落在目标区域内的墨量占比：

```json
{"feedback_id": "fb_73ea", "source": "teacher", "has_region": true,
 "revision": {"started": true, "linked": true, "latency_ms": 4000, "skipped": false},
 "before": {"strokes": 4, "points": 40, "share_in_region": 0.0},
 "after":  {"strokes": 4, "points": 40, "share_in_region": 0.75},
 "region_shift": 0.75}
```

三种结果不会塌成一种：**照着改**（`region_shift > 0`）、**改了但没改那儿**（`0.0`）、
**什么都没留下**（`null`，占比是 0/0 未定义）。被画上又立刻撤销的笔不算作回应——归因只看留在画上的笔。

### 教师 / 专家评分

`POST /api/sessions/{id}/rating` → `ratings.jsonl`，**append-only 且带 `rater_id`**：同一张画由两位老师
分别打分是常态而不是覆盖，评分者一致性是数据集必须报得出来的东西。可给 `overall`（1–5），
也可给 9 维中的任意几维（同一量表，与模型分数可比）。

`export/feedback.csv` 每条反馈一行，直接带上 `revision_started / revision_linked / latency_ms /
share_in_region_before / share_in_region_after / region_shift`——就是反馈实验的分析单元。
`export/ratings.csv` 每条评分一行。

**目前只有教师能给出区域**（AI 反馈引擎还不产出 `target_region`）。接口已经通了：等 Level 2「圈选标记」
的视觉反馈接上，把区域填进同一个字段即可，下游一行不用改。修改轮次目前是一轮，但数据模型不假设这一点——
归因是按 `feedback_id` 逐条算的，多轮反馈直接成立。

## 观摩与成就：不给孩子的画排名

需求是"推荐服务器里的佳作 + 成就系统"。**"佳作榜"这个做法被换掉了**，不是出于顾虑，
而是它和这个项目其余部分正面冲突：

1. **排名会把前面所有克制全部抵消。** 别处一直拒绝给孩子下判决——N/A 不是低分、
   徽章只读过程、结束页说"这关练的是"。佳作榜就是那个判决，只不过用社交方式送达。
2. **它是"公开一个未成年人的作品"。** 把一个孩子的画展示给另一个孩子，正是监护人
   同意书里单独勾选的那一项（`docs/ETHICS.md`）。
3. **它会污染研究。** 看过别人解法再画的孩子，已经不是任务条件的干净观测，
   Task Condition 那条线直接作废。

换成三件事：

| | 是什么 | 靠什么选 |
|---|---|---|
| **观摩** `/api/gallery/task/{id}` | 同一道题，别人**怎么画**的 | 过程签名上离你**最远**的几种做法（最远点采样），不是最好的几张 |
| **精选墙** `/api/gallery/featured` | 老师特意挑出来给大家看的 | **人的决定**，带 `rater_id`。教室墙上贴画一直是这么回事，算法给孩子排名不是 |
| **成就稀有度** `/api/achievements` | 每枚徽章有多少人点亮过 | 全服统计。「8% 的人点亮过这枚」说的是**徽章**，不是你 |

### 三道闸

- **同意**：只有 `condition.share_consent` 为真、且已完成的 session 才可能出现。
  这个字段和其他条件一样冻结在 session 里，**从不默认为真、从不推断**。
- **时机**：`gallery_display` 默认 `none`；`after_submit` 只在孩子**交完自己那张之后**
  才可见——画之前看到别人的，既会左右他画什么，也会让这次观测作废；`always` 才在首页
  显示精选墙。
- **内容**：卡片上只有作品、做法（几笔 / 几种颜色 / 几分钟 / 有没有放大）、
  和一句「他和你哪里不一样」。**没有分数、没有名字、没有暗示优劣的排序**。

「他和你哪里不一样」是真算出来的：把双方的过程签名（笔数、颜色数、工具数、时长、
撤销率、是否放大、停顿占比，全部是过程，没有一项是质量）归一化后取差异最大的那一维，
说成一句话——"用的颜色比你多"、"用更少的笔画就画完了"、"停下来想的时间更多"。

### 徽章与稀有度

徽章由客户端在结束时上报，连同**规则版本**一起存进 session。以后收紧某条规则，
不会追溯地把徽章从已经拿到的孩子手上拿走——和 `condition.json` 冻结任务定义是同一个道理。

## 个性化：历史 → 用户表示 → 新任务 → 预测

```
User → 多个任务 → 细粒度过程日志 → 用户行为历史 → 新任务 → 预测 / 个性化
```

`artquest/history.py` 是中间那根箭头：把一位被试**已完成**的 session 变成一份紧凑的
**用户表示**（User Representation），供个性化器消费。两条规则让它站得住：

1. **永远现算，不做唯一副本。** 表示每次从日志重建，所以改进构建逻辑会**追溯地**改善所有被试，
   没有任何 session 被旧摘要卡住。
2. **做决定那一刻看到的东西，本身是数据。** 一个 session 真的用了表示，那份快照就冻进
   `personalization.json`。以后重算会得到不一样（更好）的答案——那样就没人能复现当初的决定了。
   `GET /api/participants/{pid}/representation?before=<ISO>` 能重建任意历史时刻的输入。

它读**事件流**而不是笔画流：每条 `STROKE`/`ERASE` 事件已经带了 tool/color/size/点数，
所以一位被试的完整历史只花几个小文件，而不是几十 MB 的坐标。

**身份**：有研究员代号时以代号为准，`anon_id` 只在没有代号时兜底。实验室一台设备给二十个孩子用，
device id 是同一个——"任一 id 匹配"会把二十个孩子并成一个不存在的被试。

### 三臂（`artquest/personalize/`，与 `scoring/`、`feedback/` 同一套可插拔模式）

| `history_mode` | 后端 | 孩子看到 | 系统预测依据 |
|---|---|---|---|
| `none` | `no_history` | 什么都不显示 | 总体先验（量表中点）——另外两臂要打败的基线 |
| `history` | `own_history` | 1–3 条关于自己过往的短句 | 过往自评 + 任务难度差，全部可追溯到表示里的某个数 |
| `personalized` | `claude` | 模型生成的引导 | 模型读表示（输入与模板臂相同，隔离出"模型"这个变量） |

臂决定**两件互不干扰的事**：给孩子看什么（被研究的干预），和系统预测什么（**每一臂都记**，
所以预测准确率可比）。**请求了 `personalized` 但没有模型时，由模板臂代跑并如实记录**
（`requested_mode` ≠ `backend`、`available: false`）——静默降级会悄悄毁掉整个对比。

### 预测 → 自评，闭环

预测的目标是孩子**做完任务后的自评**（每个 session 本来就会产出的标签）：画之前写下预测，
交自评时打分，`personalization.json` 里落 `outcome` 与 `error`。三个条件因此是一次**评估**
而不是演示。`export/personalization.csv` 就是那张对比表
（`requested_mode / backend / n_prior_tasks / pred_* / actual_* / abs_err_*`）。

接入真正的个性化模型：在 `artquest/personalize/` 里实现 `prepare()` 并在 `get_personalizer()` 注册。

## 和已有速写数据集对齐

我们自己的落盘格式在**过程维度上是超集**，收集时这样是对的；但**一个别人读不了的格式，别人就不会用**。
所以原始日志保持原样，另出一个转换器：

```bash
python3 tools/export_sketches.py --out sketches/ --format all
```

| 格式 | 是什么 | 丢了什么 |
|---|---|---|
| `differsketching` | DifferSketching（SIGGRAPH Asia 2022）的 schema，字段逐个对照作者仓库里的样例 JSON 核过 | 逐点时间戳（只剩 `s_time`/`e_time`）、倾角、颜色、工具、缩放、参考图、停顿、每次撤销具体删了哪几笔 |
| `quickdraw` | Google QuickDraw 的 ndjson，`drawing: [[[x…],[y…],[t…]], …]` | 压感、倾角、颜色、笔宽、工具、以及全部交互过程 |
| `svg` | 纯矢量，什么都打得开 | 全部时间信息与过程 |

**和 DifferSketching 的对照**（他们的字段 = 我们的字段）：

```
strokes[].path / pressure  平行数组       ←  我们的 points 里交错的 [x,y,dt,pressure,tiltX,tiltY]
strokes[].use_pressure                    ←  pressure_supported（这一条我们各自独立得出了同一个结论）
strokes[].s_time / e_time  epoch 毫秒     ←  started_at + t_start_ms / t_end_ms
strokes[].width                           ←  size
undo_count / rm_stroke_count  只有总数     ←  我们有完整撤销时间线 + strokes_removed
（他们没有）                                ←  逐点 dt_ms、倾角、颜色、工具、缩放、参考图交互、停顿
```

每个转换出来的文件都带一个 `artquest` 块，写明**这个格式没能装下什么**，免得以后有人把转换视图
当成完整记录。`sketches/README.txt` 也会重复一遍这句话。

## 导出与回放

```bash
python3 tools/export_dataset.py --out export/ --points   # sessions/strokes/events/feedback/questionnaire(.csv)
python3 tools/replay.py <session_id> --keyframes         # 重建 + 10/25/50/75/100% 与语义关键帧
python3 tools/withdraw.py P007                          # 被试撤回（dry run；--confirm 才真删）
python3 tools/replay.py --all --check                    # 校验每个 session 都能从日志回放
```

重建走的是**事件时间线**而不是笔画列表（`artquest/reconstruct.py`）：按 `STROKE`/`ERASE` 上墨，按
`UNDO`/`REDO`/`CLEAR` 增删，最后只画留在画布上的那些笔。渲染也按笔的 `opacity` 合成，马克笔的半透明
叠加才对得上。旧 session 里 `UNDO`/`REDO`/`CLEAR` 没有 payload，退回线性撤销栈的语义（撤销弹掉最近一笔、
清空去掉全部）——除了「跨清空的撤销」，其余历史都还原得准确。

除了百分比关键帧，还会在**语义边界**上切：`before_feedback` / `after_feedback` /
`before_revision` / `after_revision`。"反馈落下时这幅画长什么样、之后又长什么样"
是反馈实验要比的那一对，而 25/50/75% 说不出来。关键帧不入库，需要时由日志现算。

## 儿童研究：身份隔离、同意与撤回

见 `docs/ETHICS.md`。要点：真实身份隔离在另一套系统，研究数据里只有匿名代号；
监护人同意 + 儿童本人同意 + **作品公开许可单独勾选**；敏感内容发布前必须逐张看过。

**撤回是整个项目里唯一"真删"的地方**——别处的原则是「只标记，不删数据」，但同意可以被收回，
那时数据必须真的消失而不是被标成可忽略。`tools/withdraw.py` 默认 dry run，
`--confirm` 才执行；名册里代号被标为撤回但**序号保留占位**，否则后来的被试会继承他的任务顺序，
在分析里悄悄变成他。回执只记「删了几个、哪些 id、什么时候」，不留任何内容。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/config` | 后端、维度定义、快照间隔、默认条件 |
| GET | `/api/families` | 10 个 mission 家族（孩子在地图上看到的） |
| GET | `/api/quests` | 全部 75 个 form（含 rubric contract 与研究元数据） |
| GET | `/api/study` · POST `/api/study/assign` | 实验配置；登记被试并返回其平衡顺序与条件 |
| POST | `/api/sessions` | 创建 session（任务、意图、身份、条件、设备、画布、study 上下文） |
| POST | `/api/sessions/{id}/log` | **批量摄取 stroke / event（幂等，可重发）** |
| POST | `/api/sessions/{id}/snapshot` | 上传中间画布（辅助） |
| POST | `/api/sessions/{id}/submit` | phase=before：评分 + 反馈；phase=after：评分 + 前后对比 + QC |
| POST | `/api/sessions/{id}/finalize` | 不修改，直接完成 + QC |
| POST | `/api/sessions/{id}/questionnaire` | 1–5 自评 |
| POST | `/api/sessions/{id}/feedback` | 记录老师 / 自评反馈（与 AI 反馈同结构，可带 `target_region`） |
| POST | `/api/sessions/{id}/rating` | 教师 / 专家评分（append-only，多评分者） |
| POST · GET | `/api/sessions/{id}/annotation` | 专家过程标注（planning / exploration / revision / organization / turning_point） |
| GET | `/api/sessions/{id}/revision` | 反馈 → 其后的修改：时间上与（有区域时）空间上的归因 |
| POST | `/api/sessions/{id}/qc` | 重跑数据质量检查 |
| GET | `/api/sessions`, `/api/sessions/{id}`, `/api/sessions/{id}/strokes` | 浏览记录 / 原始笔画 |
| GET | `/api/sessions/{id}/personalization` | 画之前系统知道什么、决定了什么（冻结） |
| GET | `/api/gallery/task/{task_id}` | 同一道题里和你做法最不一样的几张（需同意 + 条件允许） |
| GET | `/api/gallery/featured` | 老师精选墙（跨任务） |
| GET | `/api/achievements` | 每枚徽章的全服稀有度 |
| POST | `/api/sessions/{id}/badges` | 上报本次点亮的徽章及规则版本 |
| GET | `/api/participants/{pid}/protocol` | planned vs actual 任务顺序、偏离与重复 |
| GET | `/api/participants/{pid}/history` | 该被试已完成的任务（表示的输入） |
| GET | `/api/participants/{pid}/representation` | 用户表示，**每次从日志现算**；`?before=` 复现历史输入 |
| GET | `/files/{id}/...` | 图片文件 |

## 目录

```
artquest/            后端（FastAPI）
  missions.py        Creative Mission 库：M0–M9、prompt bank、卡片生成器、碎片刺激
  rubric.py          每任务的 9D rubric contract（N/A ≠ 低分，类型强制）
  quests.py          任务表（游戏关卡 = 研究 task）+ condition snapshot + tasks.json 合并
  study.py           Study Mode：条件、被试名册、平衡拉丁方顺序
  storage.py         session 存储：四个数据文件的布局 + 把旧布局折到当前形状的读取方
  events.py          统一事件词表 + 旧名折叠，stroke 字段折叠（所有读取方的唯一权威）
  logstore.py        append-only JSONL：seq 幂等追加、跑完 gzip、读写对压缩透明
  qc.py              结束时的数据质量检查
  revision.py        反馈 → 其后修改的归因（纯函数，不落库）
  gallery.py         观摩（按差异选）、精选墙（人选）、徽章稀有度
  history.py         行为历史 → 用户表示（纯函数，不落库）
  personalize/       三臂：none / history / personalized（可插拔）
  reconstruct.py     从事件时间线重建作品（replay 与 QC 共用）
  scoring/           9 维评分接口与后端
  feedback/          AI 文字反馈
  llm.py             Anthropic SDK 封装
static/              前端（原生 HTML / Canvas / JS，无构建步骤）
  app.js             界面逻辑：四个 tab、关卡地图 renderQuests、流程进度条 renderFlow、图标集 ICONS
  style.css          视觉系统（配色 / 下沿按钮 / 地图 / 徽章 / 手机与桌面两套布局）
  fonts/             Nunito 可变字重子集（SIL OFL 1.1），拉丁字母用
  log.js             本地优先记录器（IndexedDB 缓冲 + 批量补传）
tools/               export_dataset.py（CSV）、export_sketches.py（对齐已有速写数据集）
                     replay.py（回放校验 + 关键帧）、withdraw.py（被试撤回）
tests/               端到端测试 + 研究数据层测试（离线后端）
  test_personalization.py  历史 → 表示 → 三臂 → 预测打分 → 导出
  test_feedback_revision.py 区域坐标约束、反馈→修改归因、多评分者
  test_task_library.py 任务库、rubric contract、condition 冻结、protocol 平衡
  test_process_layer.py 事件词表、null 压感、生命周期、语义关键帧、过程标注、撤回
  test_gallery.py    同意闸、按差异而非质量选、人选精选、稀有度
  test_browser.py    真实 Chrome：缩放不改坐标、含撤销的 session 能重建、参考图交互、
                     鼠标压感确实是 null（无浏览器则跳过）
docs/                指南文档
```

## 下一步（Stage 2 候选，先放进指南 §06 的归类表）

- 过程节点的 9 维比较、Growth 视图
- AI 图文反馈（Level 2：圈选标记 → 填进已有的 `target_region`；Level 3：2–3 个视觉方向）
- Intent 扩展为情绪 + 目标 + 描述 / 语音
