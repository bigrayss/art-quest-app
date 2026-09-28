# KidsArtQuest — AI 美术教育游戏 App（Stage 1 · PC 核心原型）

按照 `docs/AI美术教育游戏App_分阶段开发与教育系统指南_v0.2.docx` 的 Stage 1 目标实现的最小闭环：

> 任务 → 表达意图 → 自由绘画 → 过程截图 → KidsArtBench 9 维评分 → AI 文字反馈 → 自己修改一次 → 保存 Before / After

没有 API key 也能完整跑通（离线启发式评分 + 模板反馈）；设置 `ANTHROPIC_API_KEY` 后自动切换为 Claude 视觉评分与 AI 教练反馈。

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env          # 可选：填入 ANTHROPIC_API_KEY
./run.sh                      # 默认 http://127.0.0.1:8000
HOST=0.0.0.0 ./run.sh         # 同一个 wifi 下的手机 / iPad 也能打开（会打印地址）
```

在 HPC / 远程服务器上运行时，本机执行 `ssh -L 8000:127.0.0.1:8000 <server>` 后打开浏览器访问 `http://127.0.0.1:8000`。

**给自己的 iPad 用：走 Tailscale，不要走 `HOST=0.0.0.0`。**

```bash
./run.sh 8010                                        # 还是只绑 127.0.0.1
tailscale serve --bg --https=443 http://127.0.0.1:8010
```

然后 iPad 上开 `https://<机器名>.<tailnet>.ts.net`（`tailscale status` 里看得到）。
需要：管理后台打开 **MagicDNS** 和 **HTTPS Certificates**，iPad 上装 Tailscale 客户端
并登录同一个账号。证书是 Tailscale 替你签的 Let's Encrypt 真证书。

这条路比局域网好在三处：

- **是真 HTTPS，所以 Service Worker 真的会注册**——局域网 `http://` 下浏览器
  根本不给注册，「装到主屏」装得上、图标点得开，但外壳不进设备，断网就是白屏。
  走 Tailscale 之后实测：SW `activated`、外壳存下 15 个文件、**断网重开页面照常**。
- **不用同一个 wifi**。iPad 在外面用流量也连得上。
- **默认只有自己 tailnet 里的设备看得见**，不像 `0.0.0.0` 那样把孩子的画
  摊给整个局域网。⚠️ **不要开 `tailscale funnel`**——那是把它挂到公网上。

`HOST=0.0.0.0` 那条路留着（同 wifi、对方没装 Tailscale 时应急），但它把画布和
已经收上来的作品一起暴露给整个局域网，所以是手动开、不做默认。

**拿给别人用**（别人回家也能画）是另一回事：要域名、要一份写清楚的同意书，
见 `docs/ETHICS.md`——那些还没定。

测试：

```bash
./test.sh                     # 104 项，离线后端，不需要 API key
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
| 9 | 找少量用户跑 session | 「我的」列出所有 session（研究用的 JSON 导出折在「这台设备」里）|

**明确不做**（指南 Stage 1 排除项）：图层、大量笔刷、协作、社交、积分、iOS/Android、本地模型、云端、教师/家长后台。

## 数据结构（schema 3 · 四个数据文件）

**stroke / event log 是主数据，截图只是辅助。** 一次创作一个目录（`data/` 已 gitignore，
儿童作品不要提交）：

```
data/dataset.json               数据集清单：schema、版本、各项计数（导出时刷新）
data/accounts/                  账号：一个孩子一个小 JSON + 一张索引（见「账号」一节）
data/sessions/<session_id>/
  session.json        一次任务里所有「小体量、非时间序列」的东西：身份、**冻结的任务定义**、
                      条件、设备、画布、时间、个性化、自评、QC
  strokes.jsonl       画本身，一行一笔（`.gz` 也认——见「压缩」一节，老数据里有）
  events.jsonl        所有非绘画操作——**反馈也在这条线上**，它本来就是过程中的一个事件
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

### 压缩：能力留着，默认不开

`JsonlLog.compress()` / `thaw()` 能把跑完的过程流就地压成
`strokes.jsonl.gz` / `events.jsonl.gz`——真实日志 409 KB → 50 KB，**省 88%**。
读是透明的（`JsonlLog` 两种形式都认），迟到的一批数据会先解冻再追加，
调用方不需要知道这件事。`labels.jsonl` 从不压：教师可能几周后才评分。

**但现在这条路默认不走**：`store.finalize()` 没有接在创作收尾那一步上。
理由是现在的数据量（几十个 session、几 MB）不值得用「人打不开」换那点空间——
`.gz` 在文件管理器里点开就是一屏二进制，`grep` 也搜不着，而每一个想看一眼数据的人
都要先被这一下挡住。等数据真的大起来，更该压的是**导出的那一份**
（`tools/export_dataset.py` 打包时压），而不是原始 session 目录。

`data/` 里现在**新旧混着**：2026-09-15/16 那批试跑数据带 `strokes.jsonl.gz`
（当时接着这条路），之后的不带。**老数据不动**——这个仓库里「旧 session 绝不改写」
是条铁律，为了目录看着整齐去解压它们，方向就错了。

要看压缩过的那些，用：

```bash
python3 tools/check_json.py --show data/sessions/<id>/strokes.jsonl.gz
```

### 打不开的文件：先跑一下 check_json

`data/` 目录里有一多半文件**本来就不是文本**——`final.png` 是画、
`*.jsonl.gz` 是压缩过的日志、字体是二进制。用编辑器直接打开它们会看到满屏乱码，
但那不是文件坏了。真坏的情况也有（编辑器按 GBK 存过、半路写断），
所以有 `tools/check_json.py`：逐个文件说清楚它是什么、能不能正常读出来。

```bash
python3 tools/check_json.py --dir data
```

它会报三件事：**不是 UTF-8 的**、**开头带 BOM 的**（`json.load` 会当场报错，
八成是被某个编辑器另存过）、**JSON / JSONL 解析不了的**。
另外接口返回的 JSON 一律声明 `charset=utf-8`（`Utf8JSON`）——「导出 JSON」
那条链接是给人下载下来看的，存成文件之后中文系统上的记事本和 Excel
会按 GBK 去猜，然后满屏乱码。

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

### Rubric Contract：九个维度全评，任务只说自己额外考察什么

**每幅画的九个维度都会被评分。** 一幅画总归有它的构图、线条和用色，不管它是为什么任务画的。
任务的 rubric 说的是它**额外**要诱发什么：

| 角色 | 含义 |
|---|---|
| `primary` | 任务就是为诱发它而建的，是这个任务真正测的东西 |
| `secondary` | 这里能稳定观察到，但不是任务的目的 |
| `exploratory` | **默认**：照样评分，只是不带先验。任务没提到的维度自动归这里 |
| `not_applicable` | 任务**自己的条件**让它根本产生不出来——由条件推导，任务不能自己声明 |

`primary` **不缩小评分范围**。它决定界面高亮、结束页「这一关练的是」、以及彩点哪几项属性会长，
不决定哪个维度有没有分数。

> **N/A 不是低分——而「这个任务不关心它」也不是 N/A。**

两个方向的错误一样糟：把一个任务产生不出来的维度记成 1 分，是在说"这孩子用色很差"，
一个这个任务从没测过的论断；而因为「这个任务不是讲这个的」就不评，则是悄悄停止测量
一幅画明明具备的东西。所以 `rubric.normalize()` 从任务的**条件**推导 N/A，
并**拒绝**任何条件无法justify的声明。

现在整个任务库里**没有任何任务够得着 N/A**——而且这修正了一个真实的错误：M1/M2 原来标着
「只给铅笔，所以不评颜色」，但 `allowed_tools` 限制的只是四个笔刷按钮，**调色板一直都在，
铅笔就用孩子选的颜色画**。所以 M1 的画完全可以是彩色的，它的颜色当然要评。

N/A 的机制仍然留在类型层面，给将来真的拿掉某个通道的条件用（`rubric.condition_na()`：
`allowed_tools` 里一个能上色的工具都没有时，两个色彩维度才成为 N/A）。真触发时：

- N/A 维度的分数是 `None` 加一句理由，**后端就算评了也会被抹掉**（`rubric.apply_contract`）；
- Claude 评分器**只被问可评维度**（强迫回答和真实低分无法区分）；
- 教师给 N/A 维度打分会被 **422 拒绝**；
- 前端玫瑰图上 N/A 是**虚线空槽 + 灰色标签**，不是一片短花瓣。

沉默不等于 N/A：任务没提到的维度归 exploratory，否则手滑漏掉一个维度就等于悄悄不测了。
未知维度、一个维度身兼两角、条件不支持的 N/A 声明——三者都会让任务**在加载时被拒绝**，
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

伙伴的名字**由孩子自己起**（默认占位名「彩点」，起过的名字冻进 session —— 有没有给它起名
本身就是投入程度的信号）。开场是**游戏式的三步**：先见到精灵和它的世界 → 进入世界 → 再挑任务
（`ui=quiet` 条件下整个开场不出现）。进过一次之后，这一会儿里再点「地图」就直接到关卡路径，
顶栏留一个彩点头像随时能回世界。

### 封面：不放图，主角是彩点

开场试过三版，前两版都被否掉：**九张属性卡**（像成绩单）、**我手画的一片风景**
（像随手涂的）、**一张 Unsplash 照片**（彩色墨水放大了瘆人）。现在不放图了——
这一屏的主角本来就是彩点：一片很淡的底色、一圈它自己的光、一只大彩点。

九维数据一个字段没少，只是不摆成九个东西、也不摆分数：**没画过画时彩点是灰的**，
九项里每练到一项，身后那圈光就亮一档（颜色 = 它当前的颜色，`--glow` / `--glow-a`
由 `renderWorld` 给），门口只说「颜色回来了 6/9」。要看等级和玫瑰图，
去「彩点」tab，那里本来就有。

### 说明只说一次：第一次进来的聚光灯导览

每一屏上原来都挂着一行小字说明（「画过的每一张，都收在这儿」「双指缩放移动 ·
双指轻点撤销」……）。四处小字加起来就是一层灰，而且那些话对第二次打开的孩子
毫无用处——常驻的说明书是对自己界面没信心。

第一版把它们收成了一叠居中的讲解页，还是不对：那是讲 PPT，不是指给人看。
现在是**聚光灯**：`box-shadow: 0 0 0 9999px` 把全屏压暗，一个「洞」留在正在说的
那颗按钮上（圆按钮给圆洞、方按钮给圆角方洞），旁边一张带箭头的小卡片指着它。
五步，一步一颗真按钮：

| 指着谁 | 说什么 |
| --- | --- |
| `#world-sprite` | 这是彩点。你用什么颜色，它就变什么颜色。 |
| `#btn-rename` | 点这支笔，给它起个名字。 |
| `#btn-enter-world` | 从这儿进地图。（这一步的「下一步」真的把你带进地图） |
| 第一个关卡钮 | 一个钮是一类任务。挑想画的就行。 |
| 「画廊」tab | 画过的都挂在画廊里，归你。 |

看过一次写 `artquest.guide_seen`，之后不再出现；「我的」里有「再看一遍新手指南」。
`ui=quiet` 条件下不弹（它属于游戏化那一层）。卡片位置每步实算：优先放在洞下面，
放不下就翻到上面，再夹回视口内，箭头跟着洞心走。

被删掉的小字：区块标题下的六行说明、地图顶上那行、画布和参考图下的手势提示、
自评页那行、封面那行。**留下来的只有两类**：动态的数据（时间、张数、计时）和
同意/隐私的说明（「挂上墙后别的小朋友也会看到，你说了算，随时能收回来」）——
后者不是解释，是知情权。

浏览器测试里有一条 `test_the_tour_points_at_real_buttons_and_only_shows_once`：
五步各罩住一个真元素、卡片整个留在屏内、五步说五件不同的事、走完关掉、
刷新不再拦路、「我的」里还能再打开。

### 地图：十个地方，每家占一块地

原来是「一团模糊的彩虹底 + 十个飘着的圆点」：底色发浑、和圆钮抢颜色，十个一样大的
点读起来像一排图标，不像十个地方。现在——

- 底子退成干净的纸（一层暖白渐变），**颜色只归钮和地块所有**
- **每个家族占一块自己颜色的地**（钮底下一团软色块）。宽屏是圆形色晕、
  窄屏两列时换成**方地块**（两列排下来圆晕会互相糊成一团，正是刚删掉的毛病）
- **下一关的地更大更亮，还在慢慢呼吸**（`prefers-reduced-motion` 下不动），
  彩点站在那块地上——该往哪儿走不用一行字去说
- 走过的地块淡下去，没走过的还亮着
- 钮下面那行「N 种玩法」删掉了：它是个数量，不是给孩子的话
- 大屏上地图**铺满整块屏幕**，不再是上面一张图、下面一片空白

十个家族之间**仍然没有连线**。它们本来就没有先后，一条路径会凭空承诺一个不存在的顺序。

### 房间：每块 tab 自己的空气颜色

整个 app 原来只有一种表面——白卡片、灰边框、圆角全一样，颜色只出现在按钮上，
所以排得再整齐也像一份文档。现在每块 tab 是一个**房间**：`body[data-room]` 把
`--room` / `--room-d` / `--room-l` 换成这块的主色（地图=橙、画廊=蓝、彩点=绿、
我的=紫、画画=蓝、流程=黄），三处跟着变：

- **页面底色**：顶上一层很淡的房间色光晕，往下收进 `--soft`
- **顶栏底下一条 2px 的房间色渐变线**、tab 选中态也是房间色
- **主角卡有颜色，其余保持白卡**：作品、彩点、当前任务、伙伴卡、成长面板用
  房间色的浅渐变 + 同色边（`.hero-card` 那条规则列了具体是哪几块）。
  一屏里最多两三块有色的，剩下留白，主次才出得来。

另外进每一屏时卡片**依次浮上来**（0.42s，逐级 50ms 延迟，`prefers-reduced-motion`
下自动关掉），不是整块闪一下。色值全部从已有 token 里取，没有新配色——
孩子的画仍然是屏幕上最亮的东西。

### 区块标题：一个零件，四个地方在用

「粗体标题后面拖一小段灰字」不是设计，是没设计。所以有了一个可复用的零件
`.sechead`：**一枚彩色图标砖 + 标题 + 一句人话 + 右边一个数字牌**，
颜色由用的人给（`style="--sc:...; --sc-d:..."`）。画廊的两面墙、彩点的成长、
徽章墙、观摩，五处都换成了它，数字一律收进右边那个小牌子（「6 张」「16 枚」「第 3 天」），
不再拖在标题后面。

画廊里两种卡片也重做了：自己的作品是一张**拍立得**（白边、顶上一条家族色、
下面写着哪一关和「今天 23:16」），每张按自己的 id 歪一点点，指上去就被「拿正」——
角度是定死的，不随机，每次打开都换个角度那是晃动不是手贴的。
大家那面墙上的是一张**展签**（画、几笔/几种颜色/几分钟的小胶囊、挂出来的那句话、
一行「今天挂出来的」）。
没引任何 UI 模板——这个 app 有自己的一套，套别人的只会打架。

### 每一面都按一块 pad 排

iPad 竖屏 820×1180、横屏 1180×820，两个方向都量过（脚本走一遍完整流程，
逐屏比 `scrollHeight` 和 `clientHeight`）：

| | 竖屏 | 横屏 |
| --- | --- | --- |
| 封面 / 地图 / 画廊 / 彩点 / 心愿 / 自评 | 一屏 | 一屏 |
| 创作 | 一屏（画布 768×528，占 45%） | 一屏（画布 765×526，占 64%） |
| 宝藏 | 一屏 | 一屏 |
| 我的 | 作品多了会滚——它是一张列表，本来就该滚 | 同左 |

做到这件事改了三处：
- **创作**：整屏按视口高度排，画布吃掉能给的所有高度；窄屏和竖屏把工具从「一摞卡片」
  收成**一条横带**（标签省掉、说明性的卡片收起来、主按钮占自己一行不浮在调色板上），
  横屏维持「左画布右工具栏」。画布按**能放下的那一边**缩，比例自己守住，
  缩放取点走的还是 `getBoundingClientRect`，日志和重放不受影响。
- **宝藏**：宽屏用**多栏**（`columns: 2`）而不是网格——网格的行高会把两栏锁在一起，
  左边一张大图能把右边两张卡撑成一样高，白白多出几百像素。
- **宝藏上的徽章**收成一排小章（完整的一墙在「彩点」tab），九项细节默认折起来。

| tab | 这块屏幕负责什么 |
| --- | --- |
| **地图** | 门口是彩点的世界（精灵 + 一片按九维点亮的风景 + 点亮进度）；进去是竖着蜿蜒下去的关卡地图，一个任务家族一个大圆钮，走过的盖星，彩点站在你该去的下一关旁边 |
| **画廊** | 自己的画（**画完的和没画完的都在**——半张画也是画过的证据）+ 服务器上「挂出来的画」。**两面墙空着的时候都挂在那儿**（一个虚线框 + 一句话），而不是整块消失——消失会让人以为这一屏坏了，它只是还在等第一张画。自己那面墙空着时右上角不写「0/75 种」：那是把「还没开始」写成一张成绩单 |
| **彩点** | 徽章墙（**只展示点亮过的**，剩下多少也不说，墙尾一张「?」）+ 九属性成长面板。徽章排在前面：进这一屏最想看的是「我又拿到了什么章」，那是刚发生的事；九维成长是个慢变量 |
| **我的** | 只说**用户自己**：伙伴卡、账号（名字 + 四位暗号）、小传（画完几张 / 去过几个地方 / 画了几天 / 点亮几枚，其中三块是**门**：点进画廊、地图、徽章墙）。画一张都不列——画全在画廊，同一批东西不摆两处。研究用的那几个把手——评分/反馈后端、本机代号、导出 JSON——折在「这台设备」里，原始文件路径只在实验模式下露出来 |

创作流程（心愿 → 创作 → 支招 → 进化 → 宝藏）是**盖在 tab 之上的一条流水线**：
顶栏变成「返回 + 一条细进度条 + 彩点 + 第几步」，不再占掉一整块地方。
条件里没有 AI 反馈时，支招和进化不会出现在进度里——不承诺走不到的站。

视觉规则：

| 规则 | 怎么做的 |
| --- | --- |
| **每个能按的东西都有厚度** | 按钮、卡片、关卡圆钮都有下沿，按下去 `translateY` 真的陷进去 |
| **扁平，但收着用** | 色相沿用多邻国那一套，饱和度和明度各降一档（主色橙 `#f79433`、完成绿 `#6cc24a`、次要蓝 `#4db8ef`）；一屏里只让一两块颜色说话，最亮的东西应该是孩子的画 |
| **世界与关卡是「捏出来的」** | claymorphism：一层外投影给体积，两层内投影把它吹鼓（世界卡片、属性格、关卡圆钮、进入按钮）。2026 年 iPad 上给小孩用的 app 主流就是这套软糖质感，而且它天生低饱和，跟上一条同向 |
| **iPad 当 app 用** | 装到主屏没有地址栏（外壳存在设备上，见「iPhone 和 iPad 不是同一件事」）；一根手指画、两根手指看（捏合缩放 / 拖动平移 / 双指轻点撤销，捏住的那一点不动）；见过手写笔之后手指只做手势（防手掌误触）；触摸目标 ≥44pt；画布整张看得见，窗口和转屏时按像素重算；换屏是滑进来的（画画那屏除外，动画期间祖先的 transform 会让落笔坐标偏） |
| **圆润的粗体字** | 拉丁用自托管的 Nunito，中文用自托管的**思源柔黑**（圆体）。详见下面「字体」一节——中文不自带就只能落到 PingFang SC 那种几何黑体上 |
| **不用 emoji** | 全部图标是 `app.js` 里的 `ICONS`（约 35 枚，24×24、2.2 粗描边、`currentColor`） |
| **十个任务家族各有一块颜色** | 家族色写在 `missions.py`，地图圆钮、画廊卡片、chip 走的是同一份（`styleOf`）；漏掉家族这一档的话，75 个 form 里有 70 个会退成同一个橙色 |

### 第一枚徽章：加入家庭

一打开就有，不用画任何东西。三个判断：

- **它不读任何东西**——不读过程也不读质量，就是一句「你来了」，所以它不会变成
  对孩子的判决。说明写的是事实（「你和彩点认识了」），不是夸奖。
- **它不进结算页**。它不是这一局做到的事，每次都挂个「新」就成了噪音，
  还会冲淡真正刚点亮的那几枚。
- **它不经服务器**。徽章墙平时读的是每次结算上报的记录（规则以后收紧也不会把
  已经拿到的从孩子手上取走），而这一枚不属于任何一次创作，没有哪一局能上报它。
  它是个常量不是会变的规则，所以墙上直接补（`ALL_BADGES` 里 `welcome: true`）。

顺带解决了一个问题：空墙配一句「画一幅试试」，读起来像**还没及格**。
现在第一天就有东西可看，新手导览的最后一步也有**实物**可指——
它罩的是墙上那张真卡片，不是画一个例子。

约束没有变：徽章只读过程，`ui=quiet` 依然把整套游戏化外观收起（`body.quiet`），
孩子面前不出现分数或排名。

## iPhone 和 iPad 不是同一件事

一套 WebKit，一份代码——iOS 上所有浏览器都跑 Safari 的引擎，所以不存在
「iPhone 版」和「iPad 版」两套东西要维护。但这两块屏在这个 app 里**不该是同一个角色**，
理由是量出来的，不是感觉：

| | iPad | iPhone |
| --- | --- | --- |
| 画布（1024×704，按能放下的那边缩） | 横屏 755×519、竖屏 768×528 | 竖屏 372×256，**面积只有 iPad 的四分之一**（95k vs 405k px） |
| Apple Pencil | 有：`pointerType === "pen"`，压感和倾角是真读数 | 没有：只有手指，`pressure_supported` 永远 false |
| 分屏 / Slide Over | 会把窗口压到 507 甚至 375 宽——**屏幕大不等于窗口大** | 不适用 |

第三行是设备判断必须按 **CSS 宽高**而不是按机型的原因：一台 12.9" 的 iPad 拉成
Slide Over 只有 375 宽，和一台 iPhone 一样窄。

竖着拿手机时画布是**宽度**说了算的，1024×704 塞进 393 宽的屏幕，高度最多 259——
下面那几百像素再怎么腾也变不出画布来。**横过来更糟**：852×393 的视口只剩 241 高给
整个创作区，画布反而缩到 297×204。所以手机上不劝孩子转屏，竖着就是最好的那个方向，
省下来的功夫花在省**宽度**上（页面左右 16、卡片边框和内衬 12，共 52px，是屏幕宽度的
13%，全部去掉）。

结论落到采集上：**iPad 是创作设备，iPhone 是看的设备**（画廊、我的、
家长看孩子画了什么）。手机上画得了，但一套里混着手指画的和 Pencil 画的，
stroke 流不是同一种东西——压感和倾角在一半样本里是 `null`。要合着分析，
`device.pointer_types` 和 `pressure_supported` 得当协变量，而不是当噪声。

### 三个只有真浏览器测得出来的毛病（已修；第 2、3 条只在触摸屏上犯，第 1 条桌面也中）

1. **画布被自己的框切掉**。样式表里的 `canvas { max-height: 100% }` 解析不出值：
   `.canvas-viewport` 的高度是 flex 收缩出来的，specified height 仍是 auto，
   百分比没有可依的高度，`max-height` 计算成 `none`——画布按宽度撑满、比框高出一截，
   被 `overflow: hidden` 切掉。**iPad 横屏上下各切 22px（整幅画的 7.7%），
   1440×900 的桌面各切 16px**。不只是难看：构图是九维里的一维，而孩子从来没看全过
   他被评的那个框。真正的上限现在由 `app.js` 的 `fitCanvas()` 按像素写进 style，
   窗口和转屏时重算。
2. **捏合缩放的焦点会跳**。手指给的是 `clientX/clientY`（整页的），`view.tx/ty` 量的是
   框内的位移，差着框的左上角。滚轮那条路一直减掉了 `r.left/r.top`，捏合那条路没减——
   在 iPad 上一捏，画面整个甩掉一个顶栏的高度（约 150px）。只有触摸屏走这条路，
   鼠标测不出来。
3. **矮屏落进了大屏的排版**。断点只看宽度：横过来的 iPhone 是 852×393、
   Pro Max 是 932×430，宽度够格，高度不够——十个关卡钮被塞进一条 164px 的窄带里
   **互相压住**（点「探险家速写」会点到「融合发明家」），创作屏则给了左边一条 216px
   的导航栏加右边一栏 262px 的工具，中间只剩 136px 高，画布缩成 198×136。
   两处断点都补上了高度条件（`and (min-height: 600px)` / `, (max-height: 599px)`）。

三条都有回归测试盯着：`tests/test_browser.py` 里的 `OnAnApplePad`
（六种屏幕尺寸逐一量四条边、捏合焦点、装到主屏后断网打开、画笔条挑的颜色和浓淡
能原样重建）和之前就有的 `IPadGestures`。

### 字号：全站只有一个旋钮

原来全站 **103 个字号是写死的 px**，散在各处，最常见的是 11 和 12px——而这是给小孩
在 iPad 上用的 app，iOS 给正文的建议是 17pt，12px 只有它的七成。而且 `body` 根本没设
基准字号，所以几乎全站文字都比浏览器默认的 16px 还小。

现在它们全是 `rem`，基准在 `style.css` 顶部：

```css
html { font-size: 100%; }
@media (min-width: 760px) { html { font-size: 125%; } }
```

**要整体大一点小一点，只改这一个数。** 用百分比而不是 px：px 会把用户在系统里调大的
默认字号直接盖掉，百分比是在他的设置上再乘一档。手机维持 100%（小屏幕本来就挤），
760px 以上放大到 135%——正文 12→16px，平板上实测正文 21.6px、标题 36.5px。

跟着字号走的尺寸也要用 rem，不然字大了框没大，一行反而装得更少：输入框的
`max-width` 是 `35rem` 不是 `560px`。纯布局的量（padding、边框、画布）仍然是 px。

放大之后平板竖屏的工具栏高出 26px，「撤销/重做/清空」那排被主按钮压住了。
省的办法不是把字改小回去，是**少占一行**：颜色那组是 `flex:1 1 100%`、天生自己一行，
把它排到最后，撤销那排就能跟工具和粗细挤在同一行。

**左侧导航栏可以收起**（`body.rail-off`，记在这台设备上）。

我一开始反对做这个，理由是 `body.inflow .tabbar { display:none }`——它在创作流程里
本来就已经收起来了，最缺地方的那一屏根本没有它。那条只对了一半：**字号调到 135%
之后这一栏必须变宽**（「KidsArtQuest」在 216px 里放不下，实测顶穿栏边 12px，
撞上顶栏标题），而它在四块 tab 界面上是一直占着的。能收起来，展开时才敢给够宽度——
展开 11.5rem（248px），收起 3.6rem（78px）。

两个实现上的坑：

- **栏宽必须用 rem。** 里面装的字全是 rem，栏宽写死 px，字号旋钮一调就顶穿。
  和输入框 `max-width` 那处是同一类错：容器按 px、内容按 rem。
- **变量要落在同一个元素上。** 写成 `body.rail-off { --rail-w }` 不管用：
  `.app` 自己也声明了一份，子树里赢的是它，收起状态会被原样盖回去。
  要写 `body.rail-off .app { --rail-w }`。

收起之后**图标留着**，只去掉文字——小孩靠位置和形状记路，全收光了得靠记忆找回来。

**收起键跟品牌同一行**（不单占一行），是个 22px 的**描边小方框**——次要控件，
不该比品牌还响。`margin-top:5px` 把它往下压一点，跟文字视线对齐而不是跟整行居中。
视觉 22px，但 `::before` 把可点区域撑到 **44pt**：手指够得着，布局不受影响。

加它就得腾地方，与其把整栏拉宽（那会吃画布），不如一起收：
栏宽 `10.25rem`（221px）、品牌章 26px、字号 `0.875rem`。
收起后只有 78px，品牌章和它并排放不下，改成上下叠。

**两种状态对齐的不是同一样东西**，这一条最容易做漏：

| | 对齐什么 | 怎么写 |
| --- | --- | --- |
| 展开 | **左线**——品牌章和四个 tab 图标在同一条竖线上 | `.rail-brand` 左内衬跟 `.tab` 一样 14px |
| 收起 | **中轴**——所有图标一条中线 | `body.rail-off .rail-brand { align-items:center }` |

漏掉任何一条都会看出来：收起之后品牌章、收起键、四个 tab 图标曾经分布在
中心 23–38 之间，差 15px。

**竖向同理：收起之后这一栏就是六个图标一条竖线，六个必须共用同一条节奏。**
原来是三套盒模型（品牌块有自己的内衬、收起键是裸的、tab 有 11px 上下内衬），
量出来中心间距是 `28 / 48 / 50 / 50 / 50`——第一段差 22px。
统一成「46px 的格子 + 4px 间距」= 中心间距一律 50：tab 本来就是 11+24+11=46，
所以只需要把品牌章（26，加 `margin:10px 0`）和收起键（22，加 `margin:12px 0`）
撑到同一格。

内衬**左右不对称**（`14px / 2px`）：只有左边要跟 tab 对齐，右边那个小方框
不用跟谁对齐。两边都给 14 的话品牌会被挤成「KidsArtQue…」。

顺带修了一条**从没生效过的样式**：箭头翻转原来写的是 `.rail-toggle i`，
但 `hydrateIcons()` 是 `el.outerHTML = icon(...)`——那个 `<i data-icon>` 早就被
整个换成 `<svg class="ico">` 了，选择器永远匹配不上。要写 `.rail-toggle .ico`。

### 画笔：浓淡放开给孩子，颜色不再被调色板框死

三件事，按性价比：

**1. 真正的取色器。** 原来是 12 个固定色加一个系统 `<input type=color>`。这不只是不够用——
它是**测量问题**：九维里有「色彩丰富」和「色彩对比」，而孩子能选的颜色被工具框死在 12 个里，
那两维测到的有一部分是调色板，不是孩子。现在点当前色那颗圆钮打开一个饱和度/明度面板
加一条色相（两层 CSS 渐变叠出来，不用 canvas——任何尺寸都清晰，也不用管 `devicePixelRatio`），
外加「刚用过」八格。12 个预设留着，那是给小孩的快捷键。

**2. 浓淡（不透明度）放开。** 这一条**几乎是免费的**，因为数据层早就准备好了：

```js
opacity: TOOLS[tool].alpha        // app.js：原来写死成工具属性
alpha = float(s.get("opacity"))   // reconstruct.py：一直是读这个字段
```

`reconstruct.py` 从来不查工具表，它按每一笔自己的 `opacity` 合成，连同一笔自我重叠的
`1-(1-a)^k` 都算进去了。所以把它放开成一根滑杆，**重建和 QC 一行都不用改**。
实测：40% 浓淡画四笔，重建 `rel = 0.064`（阈值 0.30，底噪 0.11–0.13）。
橡皮例外，永远 100%——它擦回初始画布，半透明的橡皮只会擦出一团脏东西。
新事件 `OPACITY_CHANGE`（是新词不是改名，旧日志里本来就没有它）。

**3. 粗细换成非线性刻度 + 笔尖预览。** 1→2 是把线加粗一倍，40→41 根本看不出来，
所以滑杆走 0–100 的均匀格子、映射到 1–60 的平方曲线，细的那头才有分辨力。
存进 stroke 的仍然是最终像素值，语义没变。旁边一个**真实大小**的笔尖点，
跟着粗细、工具倍率和浓淡走——滑杆上的「24」说不清 24px 有多粗，一个点说得清。

**没做**：更多笔型（每加一个都要在 `reconstruct.py` 里实现同样的几何，并重新标定 QC 阈值）、
图层（会把「replay = 初始画布 + stroke 流 + 事件」这条契约整个推翻）。
这两件都不是画不出来，是**要写两遍并且永远对得上**。

### 地图：先给一个默认的起点

十个任务家族一样大、一样亮地平铺着，每个还带一圈光晕。用户的原话是
「感觉给了很多主题，但是信息有点多，让人无法下手」——这是**信息架构**问题，
不是配色问题：十个平级选项、没有默认入口，孩子得一次评估十个陌生的名字才敢点。
原来确实有「下一关」的标记（彩点站在旁边），但在那堆颜色里它只是个小气泡，
不构成指引。

改了两处：

1. **地图上面加一条「从这儿开始」**（`#today`，`paintToday()`）：彩点 + 家族名 +
   一个「开始画」。它**不替孩子决定**——下面十个地方一个没少，全开着——
   它做的是让「不想决定」也能开始。走完一轮它指向下一个没走过的家族。
2. **把光晕压下去**：十个一样亮等于十个都不亮，整片糊成一袋糖。
   底色 `.3 → .13`，把对比全留给「下一关」那一个（`.52`）。

### 再收一轮：这一屏只剩两样东西

用户第二次看这一屏的原话是「信息还是太乱」。数了一下，当时**同一件事在说三遍**：
入口条说「接着往下走 · 融合发明家」，中间一条灰带说「想画别的？/ 都能去，随便挑」，
地图上那块地又亮着、彩点还站在旁边。删掉的和留下的：

- **整条灰带去掉**。它是说明书不是界面——导览第四步已经指着关卡钮说过同样的话，
  而这个项目自己定过「常驻的说明书是对自己界面没信心」。它身上唯一的信息
  （「走过 5/10 关」）并进了入口条的第一行。
- **入口条上的「N 种玩法」去掉**。地图上的同一行字早就删了（"是个数量，
  不是给孩子的话"），入口条上是漏网的那份；同一条判断没贯彻到底就是不一致。
- **入口条从一张海报收成一条**：主按钮不再占满一行，彩点小一档，
  中文的 kicker 不做 uppercase（那只会把字拆散）。手机上省出一行半。
- **窄屏上十块浅色方地只留一块**。方地曾经是为了让两列不糊成一团，但十块浅色方块
  并排，整页就读成了一张格子表。现在只有「下一关」那块有底色，其余靠圆钮自己的
  颜色和交错位置分开——一屏里最多两三块有色的，主次才出得来。
- **顶栏的录制胶囊闲着时不说话**。「等你开画」不携带任何信息，只是常驻的一块灰；
  真有事的三种情况（正在记、还没传完、断网）它自己会回来。
- 全部走完之后入口条**不再整块消失**，换成「十个地方都去过了 / 再挑一个喜欢的」
  加一个「随便来一个」——整块消失会让人以为这一屏坏了。

手机上第一屏能看到的关卡从 4 个变成 6 个。

### 第三轮：十个按钮变成十个「地方」

用户的原话是「给十个按钮感觉信息有点多、没意思」。他是对的——之前那十个圆钮
同样大小、同样形状、配一枚抽象字形，本质上是一张**图标菜单被摆歪了**，
叫地图但没有地形、没有路、也没有「我来过这儿」的痕迹。

网上的参考大致三类：多邻国那条竖着的学习路径（一条明确的路 + 一个当前位置）、
马里奥世界那种地形化的关卡图（岛屿、地标）、Toca Boca / Sago Mini 那种
「每个入口是一张有内容的插画」。第三类效果最好，但它要一整套美术资源——
19 张刺激图到现在还是印着 PLACEHOLDER 的占位图（逐张的要求见 `docs/ART_LIST.md` 第 1 节），
这条路走不通。

**所以换了个素材：孩子自己的画。**

- **去过的地方挂着自己在那儿画的最近一张画**（圆形裁切、白底、一圈家族色，
  读起来像一枚纪念章而不是一张贴上去的截图）。这是这张地图上唯一不需要美术资源、
  而且**只有这个 app 才有**的素材——一排一模一样的图标谁都做得出来，
  十扇开着自己画的窗做不到。更要紧的是这张地图会**跟着画画长出内容**：
  第一天是十块空地，画过三次之后地图上就有三扇窗。
- **没去过的地方是一块空地**：一圈虚线、颜色还没填上、没有那层厚下沿
  （厚下沿是给能按下去的东西的）。它要读起来像「这儿还没画」，
  不是像「这个按钮被禁用了」。
- **下一个该去的**保持实心家族色 + 光晕 + 彩点站在旁边——它是唯一被填满的空地。
- **一条小路把十个地方串起来**（`paintMapPath()` / `smoothPath()`）：
  按**渲染之后各个钮的真实位置**算 Catmull-Rom 平滑曲线，所以宽屏那张绝对定位的图
  和窄屏那两列交错共用同一段代码；地图藏着的时候量出来全是 0，
  所以 `show("quest")` 里还会再画一次，转屏时 debounce 重画。
  它**不带箭头、不编号、粗细也不变**：家族之间本来就没有先后，
  这条路说的是「这十个地方连在一起」，不是「按这个顺序走」。
- 挂了画的地方不再盖那颗星：那张画本身就是「来过」。

### 字体：中文必须自己带一个圆体

用户在 iPad 上的原话是「字体还是太丑了，能不能用比较圆滑的，现在太方正了」。
根因很具体：Nunito 的 `unicode-range` 把自己限死在拉丁字符，所以**界面上占绝大多数
的中文全落到 `-apple-system` 之后的 PingFang SC**——那是几何黑体，整屏看着就是方正。
**iOS 上没有预装的圆体中文**，要圆就得自己带。

用的是**思源柔黑**（Resource Han Rounded，OFL-1.1，思源黑体的圆角版本）。

中间试过悠哉字体，圆是圆了，但**它最重只到 Medium(500)**，而这个 app 大量用 600/800。
结果是全站失去粗细对比，标题不像标题了；而浏览器的「伪粗」对中文是糊的，不能用。
选字体时**字重跨度和字形一样重要**。

**体积：759KB，比只带一个字重还小。** 整包每个字重 14MB，塞不进一个要离线的 app。
`tools/build_font.py` 按实际字符集裁，而且**两份分开裁**：

| 文件 | 大小 | 字数 | 装什么 |
| --- | --- | --- | --- |
| `rhr-sc-400.woff2` | 593KB | 3924 | **正文**：GB2312 一级 + 仓库里出现过的字。孩子自己打的字（心愿、代号、给伙伴起的名）也要显示，所以要全量覆盖 |
| `rhr-sc-700.woff2` | 166KB | 1169 | **标题和按钮**：只要仓库里的字。这些文案全是写死的，孩子输入的东西永远不会加粗 |

字重区间按 `body` 的 600 划：600 落进 400 那一份（正文，全覆盖），700/800 落进
700 那一份（标题）。**划错的后果不是排版乱，是孩子打的某个字没在子集里，
那一个字会突然变成 PingFang。**

两份都在 Service Worker 的预缓存里，离线也是圆的。OFL 要求随字体分发许可证并保留
字体名称，子集的 name 表原样保留，说明写在 `static/fonts/LICENSE.txt`。

构建时需要 `pip install fonttools brotli`，**运行时不需要**。

### 装到主屏

`static/sw.js` 只做一件事：**没网的时候还能开**——HTML/CSS/JS/字体/图标/参考图
存在设备上。注意它的职责**不是**「有网的时候快一点」，这个区别在下面是要命的。

外壳之外，**装的时候还要主动抓一份那几个公共读接口**（`/api/config` `/api/quests`
`/api/families` `/api/achievements`）。原因不显然：第一次打开页面时 SW 还没接管，
那几个请求根本不经过它；不在 install 里主动抓，第一次断网冷启动就只能指望浏览器
自己的 HTTP 缓存——撞不到就是地图空白、连任务都选不了。用 `allSettled`，
少抓到一个也不该让整个 SW 装不上。

它故意不做的三件事：

- **不碰任何 POST/PUT**。孩子画的每一笔走的是 `log.js` 里 ArtLog 的 IndexedDB 队列，
  断网排在设备上、连上再补发，去重靠每条记录的 `seq`。SW 再插一手只会多出一条
  谁也说不清的重发路径。
- **不缓存 `/files/`**。那是孩子的画。撤回是这个项目里唯一一处真删，要是 SW 把作品
  留在了设备缓存里，撤回之后它还在，那条承诺就是假的。
- **不缓存带身份的 API**，也不缓存 `/api/study`（它说的是孩子跑在哪条实验臂上；
  拿一份说不清多旧的配置去渲染界面，比转个圈等服务器糟得多）。

**缓存策略：一律网络优先，缓存只做离线兜底。**

一开始写的是 stale-while-revalidate（先给存下来的，后台再更新）。听起来只是「慢一步」，
真机上的后果严重得多：HTML、CSS、JS **各自独立地过期**，于是 iPad 上出现了
**新的 HTML 配旧的 CSS 和 JS**——新加的按钮画出来了，却没有样式也没有事件，
整页看着就是坏的。外壳必须整体一致，要么全旧要么全新。

而且缓存有**两层**，只堵一层没用：

| 层 | 症状 | 堵法 |
| --- | --- | --- |
| SW 自己的 cache | 先给旧的 | `networkFirst()`，缓存只在 fetch 失败时兜底 |
| 浏览器的 HTTP 缓存 | `StaticFiles` 一个 `Cache-Control` 都不发，浏览器按**启发式**自己存，连 SW 的 `fetch` 都拿不到新的 | 服务端中间件给 `/` 和 `/static/*` 加 `no-cache`；SW 里用 `new Request(req, {cache:"reload"})` 绕过它 |

`no-cache` 不是「不缓存」，是「每次回来问一句」——文件没变就是一个 304，几十字节，
而 `StaticFiles` 本来就在发 ETag 和 Last-Modified。

**新版本装好就接手**（`skipWaiting()`）。原来写的是「等页面全关掉再说」，
看着稳妥，实际是个死锁：旧 SW 一直在发旧的 `app.js`，而「放行新版本」的逻辑
写在新的 `app.js` 里，谁也等不到谁。接手本身是安全的——已经跑起来的页面留着
它自己那份 JS。危险的是**重载页面**，那一步交给页面判断：孩子正画着就不重载
（会把没提交的一笔冲掉），下次冷启动自然就齐了。

回归测试 `test_changing_the_stylesheet_shows_up_on_the_very_next_open`：
改一个样式值，下一次打开必须就是新的。

**能离线的只有「开得起来」**：外壳 + 任务清单 + 参考图。创作本身仍然需要服务器——
`POST /api/sessions` 才拿得到 `session_id`。真要能离线创作，得让客户端先发
`session_id`、服务端认它，那是另一件事，现在没做，也别假装做了。

SW 必须从根目录发出来才管得住整个站（`/static/sw.js` 的作用域只有 `/static/`），
所以 `main.py` 里有一条 `GET /sw.js` 把它端出去，带 `no-cache` 和
`Service-Worker-Allowed: /`。浏览器缓存住旧的 `sw.js`，意味着旧的一整套外壳再也换不掉。

装新版本时**不 skipWaiting**：孩子正画到一半，脚底下不该被换掉一套 JS。
新版本等页面全关掉之后再接手。

### iOS app：同一份界面，打进包里

`ios/` 是一个 SwiftUI 工程（XcodeGen 的 `project.yml` 生成 .xcodeproj），里面只有一个 WKWebView。
`static/` 以文件夹引用整个进包，运行时从 `artquest://app/` 端出去，API 走 `https://art.ddhulu.cn/api/v1`。
Swift 只做网页做不到的事：令牌进**钥匙串**（删掉重装还在）、Apple Pencil 双击切橡皮、点亮徽章震一下、
结算页分享到相册、画画时不锁屏、`alert/confirm` 走系统弹窗。**画画引擎故意留在 JS 里**——
`reconstruct.py` 的 replay 契约是按 Canvas 标定的，换渲染器等于重标整条链。
JS 端靠页面开始前注入的 `window.ArtQuestNative = {server, token, version, platform}` 判断自己在哪个壳里；
没有它就是网页版，所有地址相对当前源。细节见 `ios/README.md`。

### 离线创作：预发的票

**孩子在没网的时候也能开一张新的。** 卡点从来不是"排队重放"——`log.js` 里
ArtLog 那套 IndexedDB 队列本来就是离线优先的，断网排队、联网补发、按 `seq` 去重。
卡点是**开工的那一刻要一个 `session_id`**。

朴素的做法是让客户端自己发一个 id。那会**一次性毁掉三样东西**：

1. **id 的可信性** —— `session_id` 是后面每张表的外键，客户端发的谁都能编。
2. **条件冻结** —— 孩子究竟跑在哪条实验臂上必须服务端说了算；让离线的设备
   自己算一遍，等于把实验设计交给设备上那份可能过期的配置。
3. **重放时的可分辨性** —— `/log` 对不认识的 session 返回 404，而 `log.js` 把
   4xx 当成"服务器拒了这一行"→ 隔离。分不清"还没建"和"不存在"的话，
   **离线画的每一笔都会被静默扔掉**：界面上一切正常，盘上什么都没有。

所以走的是**票据**：把服务端的决定**提前**，而不是拿掉。

```
POST /api/tickets   →  [{session_id, condition, quest_id, issued_at}, …]
```

联网时设备把备用名额补到 3 张（`TICKET_TARGET`）。一张票 = 服务端生成的 id +
**此刻冻好的 condition**，目录当场就占住，所以 id 不可能撞车。离线开始创作就是
花掉一张，不发任何请求；`POST /api/sessions` 带上票号，服务端认票。

| 规矩 | 为什么 |
| --- | --- |
| **条件以票上的为准**，不是花票时再算一遍 | 票是联网时发的，孩子离线跑的就是票上那条臂。重放时 `study.json` 可能已经改过，再 resolve 一次记下来的就不是孩子实际经历的东西 |
| **从没发出去的票号一律 404** | 认了编造的票号，就等于把"客户端自己发 id"从后门放回来 |
| **重复花同一张票原样返回** | 队列会重发创建，重发绝不能把一个已经有笔画的 session 抹回空的 |
| **没花掉的票不出现在任何列表里** | 它没有画、没有时间、没有任务，出现在画廊里就是一个空壳 |
| `lifecycle` 前面加了 `issued` | 排在 `recording` 前，"只进不退"那条原样成立（比的是序号） |

客户端这边，`log.js` 的 IndexedDB 升到 v2，多了两个库：

- **tickets** —— 没花掉的票
- **outbox** —— 离线时攒下的**整个请求**（建 session / 快照 / 提交 / 收尾）。
  和 `queue` 里那些逐笔记录不一样，它们各自打到不同的接口上，而且必须按原顺序重放。

`flush()` 现在先排干发件箱，再发笔画队列；被"还没建出来的 session"挡住的行这一轮
跳过（第二道防线，用在发件箱中途失败的时候）。跳过的行一条都不会删，所以
`for(;;)` 里必须有"这一轮到底动了没有"的判断，否则会原地转圈。

**回收**：每台设备联网都会补满备用名额，而设备可能再也不回来。
`python3 -m tools.reap_tickets --days 14 --apply` 把发出超过 14 天、
`lifecycle` 还是 `issued`、目录里除了 `session.json` 什么都没有的票删掉。
**删一张没花掉的票不是"删数据"**——里面从来没有孩子画过一笔，删的是一次分配；
「撤回是唯一一处真删」说的是作品。

**评分和反馈还没接上离线这条路**（用户 2026-09-16 定的：先留位置）。
它们都要服务端的 PIL，离线拿不到。等接的时候有一件事必须先想清楚：
**延后的反馈是另一种干预**——即时反馈和隔一天的反馈，对孩子改不改、怎么改的
影响完全不同，而那正是「反馈 → 修改」那条链路要测的东西。所以它得作为一个
condition 记下来（`feedback_latency: "immediate" | "deferred"`），
不能让离线和在线的数据混进同一组分析。

测试在 `tests/test_offline.py`：六条票据契约（纯 Python）+ 两条真浏览器的：

- `test_a_drawing_made_offline_arrives_complete_when_the_network_comes_back`
  ——断网画五笔、连回来、服务器上必须有这五笔且顺序不乱。做过变异验证：
  把发件箱重放去掉，那张画就根本不存在。
- `test_a_cold_launch_with_no_network_still_reaches_the_canvas`
  ——**关掉、断网、点图标重开，要一路走到画布**。这是「装到主屏」真正兑现的
  那一刻，也是最容易只兑现一半的地方。两个坑都是它抓出来的：SW 装的时候
  没抓公共接口（地图空白），以及离线开工时 IndexedDB 还没打开，
  「有 3 张票」被读成「一张都没有」。

跑在 `127.0.0.1` 上：和 HTTPS 一样算 secure context，SW 会注册。真机上这条路
要 HTTPS——**用 `tailscale serve` 就够**（见「快速开始」），2026-09-23 在真机
路径上验过：SW `activated`、缓存 `artquest-shell-<外壳哈希>` 存下 15 个文件、
断网重开四个 tab 和十个关卡都还在。

### 还没验的：真 Safari

以上全部是 Chrome（`channel="chrome"`）量的。这台机器上 Playwright 的 WebKit
装了但跑不起来——缺 `libwebkit2gtk-4.1`、`libsoup-3.0` 等系统库，装它们要 root：

```bash
sudo .venv/bin/python -m playwright install-deps webkit
```

装上之后同一批脚本换 `pw.webkit` 就能跑。在此之前，下面这些 **Safari 专有**的点
只能算「按文档应该没问题」，不算测过：`getCoalescedEvents`（Safari 给的采样率）、
Apple Pencil 的 `tiltX/tiltY` 与 `altitudeAngle`、主屏模式下的 IndexedDB 配额与清理、
`100dvh` 在 Safari 工具栏收起时的跳变。真机上一台 iPad 跑一遍比补多少仿真都值。

## Study Mode

不是「关掉游戏」，而是**固定并记录**那些本来会悄悄变化的东西。任何 session（包括自由玩）都会把
`condition` 冻结进 `metadata.json`，所以游戏化程度是一个**被记录的变量**，可以控制、也可以当自变量研究。

| 条件字段 | 取值 | 作用 |
|---|---|---|
| `ui` | `full` / `quiet` | 游戏化程度（彩点、闯关路线、徽章、画廊） |
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

**代号输入框只在实验模式下存在。** 它曾经摆在每个孩子的心愿页上（「给自己起个代号
（别用真名）」）——但代号是研究员分配的，和后端名、本机代号、导出 JSON 是同一类
把手，而这个项目早就定过：**研究用的把手不当界面给孩子看**。孩子自己的身份是
[账号](#账号让画跟着人走不是跟着一台设备)，画跟着它走。心愿页上现在只剩一句可选的
提示——「这幅画会记在这台设备上。**起个名字**，换台设备也能找回——现在不起也能画」——
点它**就地**弹注册框，不用离开这一屏、不用重挑任务；注册完那句话自己消失。
`tests/test_browser.py::test_the_researcher_code_is_not_a_thing_children_see` 守着这条。

身份是三个匿名 id 并存：设备自动生成的 `anon_id`（日常自由玩也能跨任务对齐）、
孩子自己注册的 `account_id`（换台设备还认得他，见下面「账号」一节）、
以及研究员分配的 `participant_id`。三个都不是真名。

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
| **挂出来的画** `/api/gallery/featured` | 被挑出来、**本人又答应了**的作品 | 两种挑法，都不是排名：老师 pin（带 `rater_id`）、或者每天自动轮一批（`curator/v1`，见下） |
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

### 每天自动挑一批：轮换，不是排名

墙不能只靠老师——把 app 给别人用的时候，没有老师在后台点。所以有一个每天跑一次的
策展：`POST /api/gallery/curate`，或者 cron 调 `tools/curate.py --confirm`。

**它不按评分挑，而且这不是保守：**

1. **没有「最高分」这个数可以排。** 九维是九个独立的 1–5，这个项目从不定义总分
   （`rubric.py`）；在这里发明一个，等于顺手把九个权重也发明了。
2. **离线时九个维度里有四个根本没被评**（没有 API key 就是这么跑的）。拿它排名，
   排的是墨量和颜色数，还要假装那是对画的评价。
3. 第三条才是设计上的：**每天公布一次排名，正是这个 app 拼命避免的那个判决**，
   只不过用社交方式送达。先问同意也救不回来——被问过一次然后再没被问过，本身就是判决。

挑法是**轮换 + 差异**：没上过墙的人排在最前面，一个人一轮最多一张，上过的要等
`cooldown_days`（默认 7 天）才会再轮到，在此之上用「观摩」那套最远点采样，让一批
作品覆盖不同的做法。挂出来时写的那句话是**过程事实**——「只用了 6 笔」「用了 8 种颜色」
「画完以后又改了一遍」——不是评价，也不暗示别人没做到就差。

每一张仍然只是**提议**：`curator/v1` 走的是和老师 pin 完全相同的那条路，孩子下次
打开 app 自己答应了才会挂出去。重复跑是安全的（已经提过的不再提）。

```bash
python3 tools/curate.py                 # 空跑，只打印今天会提议谁
python3 tools/curate.py --confirm       # 真的提议
0 4 * * * cd ~/ArtQuest && .venv/bin/python tools/curate.py --confirm >> logs/curate.log 2>&1
```

### 一台服务器上不止一个孩子

`/api/sessions` 不带参数返回**全部** session——那是研究员的视图，要研究员令牌（2026-09-26 起）。app 永远带着自己的
`anon_id` / `account_id` / `participant_id` 问（`mySessions()`），因为「画廊」「小传」
「地图上的星」读的都是它：一旦服务器上有第二个孩子，不带身份问就会把**别人的画**
直接放进这个孩子的个人页，绕开上面那三道闸。归属规则只有一份实现
（`storage.belongs_to`），列表、成长、个性化共用它。

### 徽章与稀有度

**只展示点亮过的。** 摆一墙灰色的未解锁徽章等于提前把惊喜说完，而且读起来像一张
「你还没做到」的清单。

**剩下多少也不说。** 曾经报过一个数（「还有 22 枚等你发现」）——看着无害，其实
把发现变回了进度条：孩子会开始数，而不是继续画。现在墙尾只留一张「?」，
它说还有，但不说有多少。界面里任何地方都不出现总数，
`tests/test_browser.py::test_the_badge_wall_never_says_how_many_are_left` 守着这条。

**触发条件是画法的形状和时机，不是阈值。** 「用 5 种以上颜色」这类条件点得亮，
但点亮的时候没人惊讶。现在 50 枚里有一整组叫**奇遇**，读的是别的东西：
整幅只用了黑白灰、擦的次数比留下的笔还多、30 笔全是小点、只有几笔但每笔都很长、
笔越换越细、结尾十笔一口气画完、夜里九点以后还在画、同一个任务又来了一次、
昨天画了今天又来。它们不写在任何地方，只能自己撞上——所以那张「?」说的是实话。

有几枚不挂在任何一次创作上（起了名字、有了账号、在两台设备上画过、挂上了墙、
连着两天来）。上报记录里不会有它们，除非孩子刚好又画完一张，所以徽章墙
**当场算一次**那些只读当下状态的规则（`litBadges()`），下一次结算再补进上报记录。

徽章由客户端在结束时上报，连同**规则版本**一起存进 session（现在是 `badges/2`）。
以后收紧某条规则，不会追溯地把徽章从已经拿到的孩子手上拿走——和冻结的任务定义
是同一个道理。

视觉上一枚章就长得像一枚章：一块捏出来的圆盘、一圈虚线托盘、底下写着名字，
**不再装在白卡片里**——一堆卡片里再放一堆卡片看着像表格。整面墙是一张收藏册内页，
章直接别在上面。稀有度只有真的少见（≤15%）时才写一句，否则每枚底下都拖着一行数字，
一面墙就读成了统计表。

**墙上不分段，也不写组名。** 「开始」「色彩与工具」「奇遇」这些词是给大人分类用的，
对着一墙章的孩子只是几行灰字；每枚章底下本来就有名字和说明，颜色也已经把组分出来了
（同一组一个色），不用再标一遍。所以整墙是一个连续的格子，按组的固定顺序排下来，
最后一枚是「?」——**一句「更多等你发现」，没有第二行解释**。

### 被选为优秀作品：先问本人

**两道闸，不是一道。** `share_consent` 回答的是「我的画可不可以被人看见」，在孩子动笔前
就冻结了；被单独挑出来当优秀作品是**另一个问题、针对另一个东西**——这一张，挂在大家面前。

所以挑中只产生一个 `pending`：作品**不会**因此出现在任何地方。孩子下次进来会看到
这张画、挑中它的那句话，和两个按钮；答应了才挂上大家那面墙，说了「先不要」就不再打扰。
自动策展（`by = curator/v1`）走的是同一条路，只是弹窗说的不是「老师选中了你的一张画」
而是「今天轮到你的画了」——它没有在评价这张画，不该借老师的嘴说话。
两个方向都可以随时改回来——画廊里自己的每张画上都有那个小标记，点一下就收回来。

状态存在 `session.json` 的 `featured` 块里（`pending` / `accepted` / `declined` + 谁选的、
什么时候），三个动作都在事件时间轴上留痕（`FEATURED_PROPOSED` / `_ACCEPTED` / `_DECLINED`）——
**拒绝也是数据**，而且必须被永久遵守。

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

**身份**：有研究员代号时以代号为准，其次是账号（`account_id`），`anon_id` 只在都没有时兜底。
实验室一台设备给二十个孩子用，device id 是同一个——"任一 id 匹配"会把二十个孩子并成一个
不存在的被试。

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

## 账号：让画跟着人走，不是跟着一台设备

在这之前「我」就是 `anon_id`——浏览器 localStorage 里的一串随机字符。它撑了很久，
因为一台电脑就是一个孩子。但[「iPhone 和 iPad 不是同一件事」](#iphone-和-ipad-不是同一件事)把 app 拆成了
**iPad 创作 / iPhone 看**，而这恰恰是 `anon_id` 做不到的事：换台设备就是换个人，
清一次缓存等于画全没了。账号补的就是这一件事。

**注册要两样东西：一个孩子自己起的名字，四位数字暗号。** 没有邮箱、没有手机号、
没有真名字段、没有密码强度提示、没有头像上传。真实身份的隔离在另一套系统里
（`docs/ETHICS.md`），账号不是身份，它只是「这些画是同一个人画的」这句话的载体。
**也不是登录墙**：不注册照样画，注册了那些画才跟着人走。入口只有一处——「我的」那一屏，
在伙伴卡下面。

### 写进代码的几条规矩（`artquest/accounts.py`）

- **名字唯一，但没有任何按名字列人的接口。** 唯一只是为了能登录。
- **暗号只存 PBKDF2-SHA256 摘要**，明文一秒都不留；连错 5 次冷却 60 秒——
  四位数字一共一万种，没有这条就等于没有暗号。「名字不存在」和「暗号不对」
  回同一句话，否则登录接口就成了「谁注册过」的查询器。
- **注册和登录从不改写任何 session。** 旧数据一个字节不动，这条和仓库里其他地方一致。
- **退出只退这一台设备**：共用 iPad 上退出的那个孩子，不该把自己手机上的登录一起弄掉。
- 伙伴的名字（`buddy_name`）跟着账号走，换台设备它还叫原来那个名字。

### 一张画归谁：`storage.belongs_to`

唯一一份归属规则，`/api/sessions`、成长、个性化历史共用它：

1. **带 `account_id` 的作品只归那个账号。** 同一台 iPad 上换个孩子登录，
   上一个孩子的画不会因为设备相同就漏过去。
2. 没有账号的作品，可以被**认领过这台设备**的账号收走，但只收**认领时刻之前**的。
3. 都不沾边，就回到原来那两个 id：研究员代号、设备代号。

**认领要孩子自己点**（「我的」里那行「这台设备上还有 N 张画没写名字，是你画的吗？」）。
自动认领在单人设备上很贴心，在教室那台共用 iPad 上是灾难：它会把上一个孩子的画
悄悄记到下一个人名下，而这正是同意闸想防的事。认领本身也不改 session——
记下来的是「这个账号认领过这台设备，截止到此刻」（`devices[].until`），
所以第 2 条里的那个时间窗才关得上：认领之后在同一台设备上无账号画的画不算数。

一台设备只能被认领一次；第二个孩子来认领会收到 409，而不是把已经有主的画抢走。

身份的**强弱顺序**（研究员代号 > 账号 > 设备）在三处共用：`history.sessions_for`、
列表行里的那个「谁」、以及墙的轮换 `gallery._person`。最后那处漏掉账号的话，
同一个孩子的 iPad 和手机会被当成两个人，轮换、一人一轮一张、cooldown 三条规则一起失效。

## 儿童研究：身份隔离、同意与撤回

见 `docs/ETHICS.md`。要点：真实身份隔离在另一套系统，研究数据里只有匿名代号；
监护人同意 + 儿童本人同意 + **作品公开许可单独勾选**；敏感内容发布前必须逐张看过。

账号也归这一节管：`tools/withdraw.py --account-id acc-…` 连账号文件一起删
（里面有孩子自己起的名字），dry run 的回执里 `accounts_seen` 会点出还有哪些账号要处理。
撤回时几个身份是**并起来**查的——分析里合并身份会捏造出一个不存在的被试，
撤回里漏掉一个身份则是答应了删除却留下了数据。

**撤回是整个项目里唯一"真删"的地方**——别处的原则是「只标记，不删数据」，但同意可以被收回，
那时数据必须真的消失而不是被标成可忽略。`tools/withdraw.py` 默认 dry run，
`--confirm` 才执行；名册里代号被标为撤回但**序号保留占位**，否则后来的被试会继承他的任务顺序，
在分析里悄悄变成他。回执只记「删了几个、哪些 id、什么时候」，不留任何内容。

## API

**路径都在 `/api/v1/` 下**（表里省掉前缀）；不带版本号的 `/api/...` 是当前版本的别名，
给 curl 和旧书签用。版本号先于 1.0 存在，因为 app 上架那天起孩子手机上的旧版本会一直调它发布那天的接口。

**三种身份，三条规矩**（`main.py`「谁在说话」那一节）：

| 谁 | 怎么证明 | 能做什么 |
|---|---|---|
| 研究员 | `Authorization: Bearer $ARTQUEST_ADMIN_TOKEN` | 表里标 🔒 的：全量列表、打分、标注、策展、QC、protocol。**不设这个变量这些接口就是关着的** |
| 账号 | `Authorization: Bearer <登录令牌>` | 凡是拿 `account_id` 当筛选 / 归属参数的地方，说自己是谁就得拿那个账号的令牌（票据例外：票是联网时拿着令牌领的，离线画完重放不用再带） |
| 设备 | 只带 `anon_id` / 知道 `session_id` | 和以前一样——它们是猜不到的随机串，尺度等同「不可猜的分享链接」 |

跨源：iOS 壳从 `artquest://app` 调这些接口，服务器用 CORS 放行（`ARTQUEST_CORS_ORIGINS`，默认就是它）。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/config` | 后端、维度定义、快照间隔、默认条件 |
| GET | `/api/families` | 10 个 mission 家族（孩子在地图上看到的） |
| GET | `/api/quests` | 全部 75 个 form（含 rubric contract 与研究元数据） |
| GET | `/api/study` · POST `/api/study/assign` | 实验配置；登记被试并返回其平衡顺序与条件 |
| POST | `/api/accounts/register` · `/api/accounts/login` | 名字 + 四位暗号；返回令牌与账号（暗号只存摘要） |
| GET | `/api/accounts/me` | 当前登录的是谁 + 这台设备上还有几张没归属的画（令牌在 `Authorization` 头里） |
| POST | `/api/accounts/claim` | 把这台设备上**此刻之前**没归属的画收进自己名下（不改 session） |
| POST | `/api/accounts/profile` · `/api/accounts/logout` | 伙伴名字跟着账号走；退出只退这一台设备 |
| POST | `/api/sessions` | 创建 session（任务、意图、身份、条件、设备、画布、study 上下文） |
| POST | `/api/sessions/{id}/log` | **批量摄取 stroke / event（幂等，可重发）** |
| POST | `/api/sessions/{id}/snapshot` | 上传中间画布（辅助） |
| POST | `/api/sessions/{id}/submit` | phase=before：评分 + 反馈；phase=after：评分 + 前后对比 + QC |
| POST | `/api/sessions/{id}/finalize` | 不修改，直接完成 + QC |
| POST | `/api/sessions/{id}/questionnaire` | 1–5 自评 |
| POST 🔒 | `/api/sessions/{id}/feedback` | 记录老师反馈（与 AI 反馈同结构，可带 `target_region`） |
| POST 🔒 | `/api/sessions/{id}/rating` | 教师 / 专家评分（append-only，多评分者） |
| POST · GET 🔒 | `/api/sessions/{id}/annotation` | 专家过程标注（planning / exploration / revision / organization / turning_point） |
| GET | `/api/sessions/{id}/revision` | 反馈 → 其后的修改：时间上与（有区域时）空间上的归因 |
| POST 🔒 | `/api/sessions/{id}/qc` | 重跑数据质量检查 |
| GET | `/api/sessions`, `/api/sessions/{id}`, `/api/sessions/{id}/strokes` | 浏览记录 / 原始笔画（`?anon_id=&account_id=&participant_id=` 只看某个孩子自己的；app 永远带）。**不带任何身份的 `GET /api/sessions` 🔒** |
| GET | `/api/sessions/{id}/personalization` | 画之前系统知道什么、决定了什么（冻结） |
| GET | `/api/gallery/task/{task_id}` | 同一道题里和你做法最不一样的几张（需同意 + 条件允许） |
| GET | `/api/gallery/featured` | 挂出来的画（跨任务，老师 pin + 每天轮到的，都要本人答应过） |
| POST 🔒 | `/api/gallery/curate` | 挑出今天要挂的一批（只提议；轮换 + 差异，不排名） |
| GET | `/api/achievements` | 每枚徽章的全服稀有度 |
| POST | `/api/sessions/{id}/badges` | 上报本次点亮的徽章及规则版本 |
| GET 🔒 | `/api/participants/{pid}/protocol` | planned vs actual 任务顺序、偏离与重复 |
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
  accounts.py        账号：名字 + 四位暗号、令牌、设备认领（让画跟着人走）
  storage.py         session 存储：四个数据文件的布局 + 把旧布局折到当前形状的读取方
  events.py          统一事件词表 + 旧名折叠，stroke 字段折叠（所有读取方的唯一权威）
  logstore.py        append-only JSONL：seq 幂等追加、读写对压缩透明（压缩能力留着，默认不开）
  qc.py              结束时的数据质量检查
  revision.py        反馈 → 其后修改的归因（纯函数，不落库）
  gallery.py         观摩（按差异选）、挂出来的画（人选 + 每天轮换）、徽章稀有度
  history.py         行为历史 → 用户表示（纯函数，不落库）
  personalize/       三臂：none / history / personalized（可插拔）
  reconstruct.py     从事件时间线重建作品（replay 与 QC 共用）
  scoring/           9 维评分接口与后端
  feedback/          AI 文字反馈
  llm.py             Anthropic SDK 封装
ios/                 iOS app：Swift 壳（WKWebView + 钥匙串 + Pencil 双击 + 分享），界面就是下面这份 static/
                     整个打进包里。构建方式见 ios/README.md
static/              前端（原生 HTML / Canvas / JS，无构建步骤；网页版和 iOS app 共用同一份）
  app.js             界面逻辑：四个 tab、关卡地图 renderQuests、流程进度条 renderFlow、图标集 ICONS
  style.css          视觉系统（配色 / 下沿按钮 / 地图 / 徽章 / 手机与桌面两套布局）
  fonts/             Nunito 可变字重子集（SIL OFL 1.1），拉丁字母用
  log.js             本地优先记录器（IndexedDB 缓冲 + 批量补传）
tools/               check_json.py（数据目录体检）、gen_art_list.py（生成配图清单）
                     export_dataset.py（CSV）、export_sketches.py（对齐已有速写数据集）
                     replay.py（回放校验 + 关键帧）、withdraw.py（被试撤回）
tests/               端到端测试 + 研究数据层测试（离线后端）
  test_personalization.py  历史 → 表示 → 三臂 → 预测打分 → 导出
  test_feedback_revision.py 区域坐标约束、反馈→修改归因、多评分者
  test_task_library.py 任务库、rubric contract、condition 冻结、protocol 平衡
  test_process_layer.py 事件词表、null 压感、生命周期、语义关键帧、过程标注、撤回
  test_gallery.py    同意闸、按差异而非质量选、人选 / 自动轮换、稀有度
  test_accounts.py   注册 / 登录 / 冷却、共用设备上谁也看不见谁、认领只收认领前的
  test_app_api.py    /api/v1 与别名、CORS 预检、研究员令牌、account_id 必须配令牌；
                     真实 Chrome 里把外壳放到第二个源上跑一遍登录 + 开画（= iOS 壳的 JS 那一半）
  test_browser.py    真实 Chrome：缩放不改坐标、含撤销的 session 能重建、参考图交互、
                     鼠标压感确实是 null（无浏览器则跳过）
docs/                ART_LIST.md（美术清单：要画的参考图 19 张 / 地图字形 10 枚 / 徽章 51 枚 / app 图标，
                     每项写像素尺寸、文件名、画什么；由 gen_art_list.py 从代码生成）、ETHICS.md、开发指南
```

## 下一步（Stage 2 候选，先放进指南 §06 的归类表）

- 过程节点的 9 维比较、Growth 视图
- AI 图文反馈（Level 2：圈选标记 → 填进已有的 `target_region`；Level 3：2–3 个视觉方向）
- Intent 扩展为情绪 + 目标 + 描述 / 语音
