# 彩绘冒险 · KidsArtQuest

给孩子和成年初学者的 AI 美术教育游戏，也是一个研究数据采集平台。
孩子选一道题，画完得到一句反馈，可以改一次再交；每一笔和每一次操作都记在时间线上。

- 网页版 `static/`：原生 HTML / Canvas / JS，没有构建步骤
- 后端 `artquest/`：FastAPI，一次创作一个目录
- iOS `ios/`：Swift 壳里装同一份 `static/`
- 线上：https://art.ddhulu.cn/

设计说明（每个决定为什么这样做）在 [`DESIGN.md`](DESIGN.md)。

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env     # 可选：填模型 key 才会用 AI 评分和反馈
./run.sh                 # http://127.0.0.1:8000
./test.sh                # 全部测试，离线，不需要 key
```

没有 key 时用离线启发式评分和模板反馈，整个流程照样能跑。模型挂了也会自动退回这两样。
浏览器测试用系统的 Chrome；没装 Playwright 或没有 Chrome 就自动跳过。

## 配置

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `ARTQUEST_LLM_BASE_URL` · `ARTQUEST_LLM_API_KEY` | 空 | OpenAI 兼容接口（现用华东师大 ecnu-plus） |
| `ANTHROPIC_API_KEY` | 空 | 另一条通路；两种都给时走 OpenAI 兼容那条 |
| `ARTQUEST_MODEL` | `ecnu-plus` | 模型名 |
| `ARTQUEST_SCORER` · `ARTQUEST_FEEDBACK` | `auto` | `auto` / `llm` / `heuristic` 或 `template` |
| `ARTQUEST_SELECTION_AUTHORITY` | `client` | 选题权威：`client` 浏览器算、服务端影子对照；`server` 服务端算好发给浏览器 |
| `ARTQUEST_LLM_TOOLS` | `off` | 模型后端是否支持工具协议（agent 选题臂要）；ecnu 已实测可设 `native` |
| `ARTQUEST_DATA_DIR` | `./data` | 数据目录，不进仓库 |
| `ARTQUEST_ADMIN_TOKEN` · `ARTQUEST_TEACHER_CODE` | 空 | 研究员令牌、老师邀请码 |

## 部署

```bash
./deploy/push.sh      # rsync 到服务器 + 重启 systemd --user 服务
```

细节在 [`deploy/README.md`](deploy/README.md)。

## 数据

一次创作一个目录：

```
data/sessions/<id>/
  session.json    身份、冻结的任务、条件、评分、这道题怎么来的
  strokes.jsonl   一行一笔
  events.jsonl    所有非绘画操作，反馈也在这条线上
  labels.jsonl    教师评分、专家标注
  calls.jsonl     每次模型 / 引擎执行一条
  final.png       交上来的作品
  frames/         陪伴每次点击那一刻的画布
```

导出成 CSV：`tools/export_dataset.py`。字段含义和选题（影子、权威、三臂）的设计在 `DESIGN.md`。

## 目录

```
artquest/   后端：任务库 · 实验配置 · 账号 · 存储 · 事件词表 · 评分 / 反馈 / 陪伴 · 选题
static/     前端：app.js · style.css · log.js · 中英文 · 精灵素材 · 参考图
ios/        Swift 壳
deploy/     推送脚本、服务、接入指南
tools/      生成清单、导出数据集、探测、回放、撤回
tests/      端到端 + 数据层测试
docs/       试点流程、任务清单、文案清单、伦理说明
```
