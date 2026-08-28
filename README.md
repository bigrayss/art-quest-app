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
python3 -m unittest -v
```

## 已实现（对应指南 §02 / §08 开发顺序）

| # | 指南要求 | 实现 |
|---|---|---|
| 1 | PC 画布 + 3–4 种基础工具 | 铅笔 / 笔刷（支持数位板压感）/ 马克笔（半透明）/ 橡皮，调色盘 + 自定义颜色，粗细，Undo / Redo（Ctrl+Z / Ctrl+Y），清空 |
| 2 | 保存最终作品 | 服务器保存 `before.png` / `after.png`；也可下载到本机 |
| 3 | 定时保存中间图片 | 每 45 s（`ARTQUEST_SNAPSHOT_INTERVAL`）上传一张画布快照；同时记录换工具 / 换颜色 / 撤销 / 清空等事件 |
| 4 | 3–5 个 Creative Quest | 5 个：情绪表达、想象、Transformation、Color/Composition、Story（`artquest/quests.py`） |
| 5 | Intent 输入 | 画前情绪（chips）+ 一句话意图 |
| 6 | KidsArtBench 9 维评分 | 可插拔接口 `artquest/scoring/`：`claude`（结构化 JSON 输出）/ `heuristic`（离线） |
| 7 | AI 文字反馈 | `artquest/feedback/`：三段式「我看到 / 一个问题 / 可以试试」，遵守“帮助思考、不替代创作、不给标准答案、不提分数”的原则 |
| 8 | 修改并保存 Before / After | 反馈后可修改一次（或跳过），再次评分 + 前后对比评语，展示 9 维差值 |
| 9 | 找少量用户跑 session | 首页「作品记录」可浏览所有 session，直接打开图片与 JSON |

**明确不做**（指南 Stage 1 排除项）：图层、大量笔刷、协作、社交、积分、iOS/Android、本地模型、云端、教师/家长后台。

## 数据结构

每次创作一个目录（`data/` 已 gitignore，儿童作品不要提交）：

```
data/sessions/<id>/
  session.json        任务、意图、事件时间线、快照列表、before/after 评分、反馈、对比
  snapshots/0001_45s.png ...
  before.png          反馈前
  after.png           修改后（未修改时与 before 相同，revised=false）
```

## 评分与反馈后端

| 环境变量 | 取值 | 说明 |
|---|---|---|
| `ARTQUEST_SCORER` | `auto` / `claude` / `heuristic` | auto：有 key 用 claude |
| `ARTQUEST_FEEDBACK` | `auto` / `claude` / `template` | 同上 |
| `ARTQUEST_MODEL` | 默认 `claude-opus-5` | |
| `ARTQUEST_EFFORT` | 默认 `medium` | Opus 5 自适应思考，effort 控制深度 |

接入正式 KidsArtBench 模型：在 `artquest/scoring/` 新增一个实现 `Scorer` 协议的类（输入 PNG bytes + quest + intent，输出 9 维分数与说明），并在 `get_scorer()` 中注册。9 维定义见 `artquest/scoring/base.py`（当前 1–10 分，可按官方量表调整）。

`heuristic` 后端只对色彩 / 线条 / 画面组织有信号，写实、变形、想象、转化四个语义维度返回中间值并标注“需模型评分”。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/config` | 后端、维度定义、快照间隔 |
| GET | `/api/quests` | 任务列表 |
| POST | `/api/sessions` | 创建 session（quest_id, intent, participant） |
| POST | `/api/sessions/{id}/snapshot` | 上传中间画布 + 事件 |
| POST | `/api/sessions/{id}/submit` | phase=before：评分 + 反馈；phase=after：评分 + 前后对比 |
| POST | `/api/sessions/{id}/finalize` | 不修改，直接完成 |
| GET | `/api/sessions`, `/api/sessions/{id}` | 浏览记录 |
| GET | `/files/{id}/...` | 图片文件 |

## 目录

```
artquest/            后端（FastAPI）
  quests.py          Creative Quest 定义
  scoring/           9 维评分接口与后端
  feedback/          AI 文字反馈
  llm.py             Anthropic SDK 封装
  storage.py         session 文件存储
static/              前端（原生 HTML / Canvas / JS，无构建步骤）
tests/               端到端测试（离线后端）
docs/                指南文档
```

## 下一步（Stage 2 候选，先放进指南 §06 的归类表）

- 更完整的 Drawing Timeline（笔触级事件）与 session 导出
- 过程节点的 9 维比较、Growth 视图
- AI 图文反馈（Level 2：圈选标记；Level 3：2–3 个视觉方向）
- Intent 扩展为情绪 + 目标 + 描述 / 语音
