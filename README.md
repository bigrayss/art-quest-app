# 彩绘冒险 · KidsArtQuest

给 6–14 岁孩子的 AI 美术教育游戏，同时是一个研究数据采集平台。
孩子在地图上选一个主题，写下想画什么，画完得到一句反馈，可以改一次再交；
画的每一笔和每一次操作都记在时间线上，供后续研究分析。

- 网页版：`static/`，原生 HTML / Canvas / JS，没有构建步骤
- 后端：`artquest/`，FastAPI，一次创作一个目录
- iOS app：`ios/`，Swift 壳里装的是同一份 `static/`
- 线上：https://art.ddhulu.cn/

完整的设计说明（每个决定为什么这样做）在 [`DESIGN.md`](DESIGN.md)。

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env     # 可选：填模型 key（ecnu-plus 或 Anthropic）才会用 AI 评分和反馈
./run.sh                 # http://127.0.0.1:8000
./test.sh                # 全部测试，离线，不需要 API key
```

没有 API key 时用离线启发式评分和模板反馈，整个流程照样能跑通。
`tests/test_browser.py` 等几组会用系统的 Chrome 真跑一遍；没装 Playwright 或没有 Chrome 就自动跳过
（`.venv/bin/pip install playwright`，不必 `playwright install`）。

给 iPad 试用走 Tailscale（`tailscale serve --bg --https=443 http://127.0.0.1:8010`），
不要用 `HOST=0.0.0.0`：后者把孩子的画暴露给整个局域网，而且不是 HTTPS，装到主屏后断网是白屏。

## 配置

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `ARTQUEST_LLM_BASE_URL` · `ARTQUEST_LLM_API_KEY` | 空 | 任何 OpenAI 兼容接口。华东师大 ecnu-plus：`https://chat.ecnu.edu.cn/open/api/v1` |
| `ANTHROPIC_API_KEY` | 空 | 另一条路：Anthropic。两种 key 都给时走 OpenAI 兼容那条 |
| `ARTQUEST_SCORER` | `auto` | `auto` / `llm` / `heuristic`（`claude`、`ecnu` 都当 `llm`） |
| `ARTQUEST_FEEDBACK` | `auto` | `auto` / `llm` / `template`，陪伴跟它走 |
| `ARTQUEST_MODEL` · `ARTQUEST_EFFORT` | `ecnu-plus` 或 `claude-opus-5` · `medium` | 模型与思考深度（ecnu 默认不开思维链，`ARTQUEST_LLM_THINKING=1` 才开） |
| `ARTQUEST_DATA_DIR` | `./data` | 数据目录，已 gitignore，儿童作品不进仓库 |
| `ARTQUEST_SNAPSHOT_INTERVAL` | `45` | 过程截图间隔（秒） |
| `ARTQUEST_ADMIN_TOKEN` | 空 | 研究员令牌；不设则全量列表、打分、策展等接口一律 401 |
| `ARTQUEST_TEACHER_CODE` | 空 | 老师注册的邀请码 |
| `ARTQUEST_CORS_ORIGINS` | iOS 壳的源 | 跨源来源 |

## 部署

```bash
./deploy/push.sh      # rsync 到服务器 + 重启 systemd --user 服务
```

服务器只监听 `127.0.0.1:8010`，对外由机器上已有的 Caddy 反代，不需要 sudo。
细节和踩过的坑在 [`deploy/README.md`](deploy/README.md) 和 [`deploy/服务器接入指南.md`](deploy/服务器接入指南.md)。

## 数据

一次创作一个目录，四个数据文件加一张图：

```
data/sessions/<id>/
  session.json    身份、冻结的任务定义、条件、设备、画布、自评、QC
  strokes.jsonl   画本身，一行一笔
  events.jsonl    所有非绘画操作，反馈也在这条线上
  labels.jsonl    教师评分、专家标注
  final.png       交上来的作品
```

原则：不高频、不是时间序列的进 `session.json`；能算出来的不存。
事件词表的唯一权威是 `artquest/events.py`。研究员接口见 `DESIGN.md` 的「API」一节。

## 研究相关

- **任务库**：十个主题家族，每家 2 道两版共通的锚定题加小学 3 道、初中 3 道，题面在 `artquest/missions_v2.py`（当前 2.6 版）。
  题面是研究材料，改一个字都要升 `TASK_VERSION`。
- **Study Mode**：条件（游戏化程度、能否看参考图、能否撤销、历史模式）冻进每个 session，`artquest/study.py`。
- **评分**：九个维度 1–5 分，离线启发式或 Claude 视觉评分，可插拔（`artquest/scoring/`）。
- **伦理**：`docs/ETHICS.md`；隐私政策页 `/privacy`。

## 目录

```
artquest/     后端：missions_v2 任务库 · study 实验配置 · accounts 账号 · storage 存储 · events 事件词表
              scoring / feedback / assist 三个可插拔的 AI 入口 · gallery 观摩与徽章 · qc 数据质量
static/       前端：app.js 界面 · style.css · log.js 本地优先记录 · i18n.js + lang/en.js 中英文
              art/buddy 彩点六个形象 · refs 参考图
ios/          Swift 壳，见 ios/README.md
deploy/       推送脚本、systemd 服务、Caddy 片段、接入指南
tools/        生成清单（任务 / 文案 / 美术）、出精灵素材、导出数据集、回放、撤回
tests/        端到端 + 研究数据层测试
docs/         给人看的：试点测试流程、任务清单、文案清单、美术清单、伦理说明、原始开发指南
art-src/      精灵的原始素材（tools/build_buddy_roles.py 的输入）
```

## 文档

| 想知道 | 去哪 |
|---|---|
| 为什么这样设计、每个模块的契约 | `DESIGN.md` |
| 第一次试点怎么组织 | `docs/试点测试流程.md` |
| 80 道题面 | `docs/任务清单.pdf` |
| 界面上每一句话 | `docs/文案清单.md`（`tools/gen_copy_list.py` 生成） |
| 美术资源 | `docs/ART_LIST.md`（`tools/gen_art_list.py` 生成） |
| 彩点怎么做的 | `static/art/buddy/README.md` |
