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
./test.sh                     # 36 项，离线后端，不需要 API key
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

## 数据结构（schema 2 · 研究级过程数据）

**stroke / event log 是主数据，截图只是辅助。** 每次创作一个目录（`data/` 已 gitignore，儿童作品不要提交）：

```
data/sessions/<id>/
  metadata.json       身份、任务、条件、设备、时间、计数、QC 结果
  events.jsonl        append-only 操作日志：{seq, src, ts, t_ms, type, payload}
  strokes.jsonl       append-only 逐笔记录 + 采样点（见下）
  feedback.jsonl      每一条反馈：{feedback_id, source, feedback_type, text, target_region, shown_at}
  ratings.jsonl       教师 / 专家评分，append-only 带 rater_id（支持多评分者）
  questionnaire.json  1–5 轻量自评（难度 / 满意度 / 开心程度 / 最难的地方）
  personalization.json 画之前冻结的表示、给孩子看了什么、预测了什么，以及事后的 outcome / error
  before.png / after.png / final.png
  snapshots/0001_45s.png ...   （辅助，关键帧可由 stroke log 动态重建）
```

一条 stroke（原始数据只存不算，speed / hesitation / rhythm 一律留给离线分析）：

```json
{"seq": 12, "stroke_id": "s00012", "phase": "before", "t_start_ms": 48210, "t_end_ms": 48930,
 "tool": "brush", "color": "#e63946", "size": 6, "opacity": 0.9, "erase": false, "pointer_type": "pen",
 "zoom": 4.0, "points": [[x, y, dt_ms, pressure, tiltX, tiltY], ...]}
```

`points` 用画布像素坐标（`metadata.canvas` 记录画布尺寸，保证可复现），`dt_ms` 相对 `t_start_ms`；
`pointermove` 走 `getCoalescedEvents()`，数位板可拿到完整输入率（可达 ~240 Hz）。

**缩放不进坐标。** 缩放 / 平移是画布元素上的一个 CSS transform，绘图上下文完全不知情；指针坐标经
`getBoundingClientRect()` 换算，而它返回的正是变换后的盒子——所以 8 倍放大下画的笔，和 100% 下画的笔
落在同一个坐标系里，replay、undo、快照全都不受影响。`zoom` 字段记的是**当时孩子能看到什么**，那是另一个问题
（"什么时候放大去抠细节"本身就是过程信号）。这条不变式由 `tests/test_browser.py` 在真实 Chrome 里验证。

事件类型：`SESSION_START` `STROKE` `ERASE` `UNDO` `REDO` `CLEAR` `BRUSH_CHANGE` `COLOR_CHANGE`
`SIZE_CHANGE` `REFERENCE_OPEN` `REFERENCE_CLOSE` `IDLE_START` `IDLE_END` `TIME_LIMIT_REACHED`
`FEEDBACK_SHOWN` `REVISION_START` `REVISION_SKIPPED` `QUESTIONNAIRE_SUBMITTED` `SESSION_END` `DOWNLOAD`。
`FEEDBACK_SHOWN` 带 `feedback_id`，是切分「反馈前 / 反馈后」行为的锚点。

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

## 任务系统 = 游戏关卡（一张表，两种读法）

孩子看到的「关卡」和研究者读到的「task」是同一行数据（`task_id == quest.id`）。开放创作任务取的是每个
研究字段的**宽松取值**（`reference: null` / `time_limit_sec: null` / `allowed_tools: null` = 全部工具）——
这是合法的条件取值，不是缺字段。约束更紧的题就是同一张表里字段更紧的几行，因此 user effect 与 task effect
天然可分，不需要第二套任务系统。

研究者不改代码就能加题：把一个 JSON 列表放到 `$ARTQUEST_DATA_DIR/tasks.json`，按 `id` 合并覆盖内置任务。

```json
[{"id": "shape_basic", "type": "观察", "title": "照着画：三个基本形状",
  "prompt": "……", "category": "observation", "difficulty": 1,
  "time_limit_sec": 300, "allowed_tools": ["pencil", "eraser"],
  "reference": {"id": "shapes_a", "file": "/static/refs/shapes_a.png", "mode": "on_demand"},
  "focus_dims": ["realism", "line_texture"], "icon": "🔺", "color": "#2b7de8"}]
```

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

## 导出与回放

```bash
python3 tools/export_dataset.py --out export/ --points   # sessions/strokes/events/feedback/questionnaire(.csv)
python3 tools/replay.py <session_id> --keyframes         # 从日志重建作品 + 10/25/50/75/100% 关键帧
python3 tools/replay.py --all --check                    # 校验每个 session 都能从日志回放
```

重建走的是**事件时间线**而不是笔画列表（`artquest/reconstruct.py`）：按 `STROKE`/`ERASE` 上墨，按
`UNDO`/`REDO`/`CLEAR` 增删，最后只画留在画布上的那些笔。渲染也按笔的 `opacity` 合成，马克笔的半透明
叠加才对得上。旧 session 里 `UNDO`/`REDO`/`CLEAR` 没有 payload，退回线性撤销栈的语义（撤销弹掉最近一笔、
清空去掉全部）——除了「跨清空的撤销」，其余历史都还原得准确。

关键帧不入库，需要时由日志现算。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/config` | 后端、维度定义、快照间隔、默认条件 |
| GET | `/api/quests` | 任务列表（含研究元数据） |
| GET | `/api/study` · POST `/api/study/assign` | 实验配置；登记被试并返回其平衡顺序与条件 |
| POST | `/api/sessions` | 创建 session（任务、意图、身份、条件、设备、画布、study 上下文） |
| POST | `/api/sessions/{id}/log` | **批量摄取 stroke / event（幂等，可重发）** |
| POST | `/api/sessions/{id}/snapshot` | 上传中间画布（辅助） |
| POST | `/api/sessions/{id}/submit` | phase=before：评分 + 反馈；phase=after：评分 + 前后对比 + QC |
| POST | `/api/sessions/{id}/finalize` | 不修改，直接完成 + QC |
| POST | `/api/sessions/{id}/questionnaire` | 1–5 自评 |
| POST | `/api/sessions/{id}/feedback` | 记录老师 / 自评反馈（与 AI 反馈同结构，可带 `target_region`） |
| POST | `/api/sessions/{id}/rating` | 教师 / 专家评分（append-only，多评分者） |
| GET | `/api/sessions/{id}/revision` | 反馈 → 其后的修改：时间上与（有区域时）空间上的归因 |
| POST | `/api/sessions/{id}/qc` | 重跑数据质量检查 |
| GET | `/api/sessions`, `/api/sessions/{id}`, `/api/sessions/{id}/strokes` | 浏览记录 / 原始笔画 |
| GET | `/api/sessions/{id}/personalization` | 画之前系统知道什么、决定了什么（冻结） |
| GET | `/api/participants/{pid}/history` | 该被试已完成的任务（表示的输入） |
| GET | `/api/participants/{pid}/representation` | 用户表示，**每次从日志现算**；`?before=` 复现历史输入 |
| GET | `/files/{id}/...` | 图片文件 |

## 目录

```
artquest/            后端（FastAPI）
  quests.py          任务表（游戏关卡 = 研究 task，含研究元数据 + tasks.json 合并）
  study.py           Study Mode：条件、被试名册、平衡拉丁方顺序
  storage.py         session 存储（metadata + 三条 append-only 流）
  logstore.py        JSONL append-only 写入与幂等去重
  qc.py              结束时的数据质量检查
  revision.py        反馈 → 其后修改的归因（纯函数，不落库）
  history.py         行为历史 → 用户表示（纯函数，不落库）
  personalize/       三臂：none / history / personalized（可插拔）
  reconstruct.py     从事件时间线重建作品（replay 与 QC 共用）
  scoring/           9 维评分接口与后端
  feedback/          AI 文字反馈
  llm.py             Anthropic SDK 封装
static/              前端（原生 HTML / Canvas / JS，无构建步骤）
  log.js             本地优先记录器（IndexedDB 缓冲 + 批量补传）
tools/               export_dataset.py（导出 CSV）、replay.py（回放校验 + 关键帧）
tests/               端到端测试 + 研究数据层测试（离线后端）
  test_personalization.py  历史 → 表示 → 三臂 → 预测打分 → 导出
  test_feedback_revision.py 区域坐标约束、反馈→修改归因、多评分者
  test_browser.py    真实 Chrome：缩放不改坐标、含撤销的 session 能重建（无浏览器则跳过）
docs/                指南文档
```

## 下一步（Stage 2 候选，先放进指南 §06 的归类表）

- 过程节点的 9 维比较、Growth 视图
- AI 图文反馈（Level 2：圈选标记 → 填进已有的 `target_region`；Level 3：2–3 个视觉方向）
- Intent 扩展为情绪 + 目标 + 描述 / 语音
