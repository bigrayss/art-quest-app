# 彩点

界面里**十处**彩点都走这里（`paintBuddy()` / `buddyHtml()`）：门口 · 顶栏小头像 · 过程条 ·
「彩点的世界」大图 · 画画屏右栏 · 支招页 · 问卷页 · 对比页 · 地图上「你在这儿」和「今天」卡。

## 素材来源

| 文件 | 来源 | 尺寸 |
| --- | --- | --- |
| `hero.webp` | v2 包的 `01_body.png` | 1312×1199，**活动区留空** |
| `hero-hand.webp` | v2 `02_hand_motion.png`，每 2 帧取 1 帧重排 | 6×5 格，每格 242×278，30 帧 |
| `hero-feet.webp` | v2 `03_feet_motion.png`，同上 | 6×5 格，每格 513×250，30 帧 |
| `hero-eyes.webp` | v2 `04_blink_sprite.png` | 9×1 格，每格 329×196 |
| `icon.webp` / `icon-happy.webp` | 从 `00_original.png` 裁贝雷帽和圆身子 | 256×256 |

出素材的脚本：`tools/build_buddy_roles.py`（`normal_rig()` 那段；换素材重跑一次，会打印 CSS 的位置百分比）。
原始包在 `docs/彩绘精灵_眨眼与手脚微动_v2.zip`，用户 2026-10-04 给的，里面带 `rig.json`、
参考实现 `mascot.css` 和校验 `validation.json`。`00_original.png` 和
`docs/橙色贝雷帽的开心小画家.png` **sha256 一致**，是同一张。

## 动的是局部，不是整只

身体那张图把**右手 / 双脚 / 眼睛**三块挖空，三张帧图用 CSS `steps()` 走格子盖上去。
拿铅笔的那只手和铅笔**不动**。每 3 秒一轮手脚，6 秒里眨两次眼（1.4s 和 4.45s），
一次闭合+睁开约 0.30 秒。整只不浮动（用户：「整體浮動沒什麼用」）。

**位置百分比（`.bd-hand/.bd-feet/.bd-eyes` 的 left/top/width/height）由 `tools/build_buddy_roles.py`
的 `normal_rig()` 打印，别自己改**——帧图和原图 1312×1199 的坐标是绑死的。
2026-10-04 起三张帧图**每格四周留 2px 透明缝**（`GUTTER`），框也跟着外扩 2px：没有缝的话精灵一做缩放动画
（呼吸、戳一下），格子边缘的采样会把隔壁那一格的身体像素渗进来，屏幕上多一条细线。帧图仍是原生分辨率。

### ⚠️ 两个踩过的坑

1. **`.sprite.hero` 的 `max-width` 不能把宽度夹住。** 身体图是 `object-fit`，夹住就会居中留边，
   而三块活动区按**元素**的百分比定位——元素一旦不是 1312:1199，两者错开，屏幕上会露出
   一整块方框（线上出现过）。现在 `max-width:100%` + `aspect-ratio:1312/1199`，
   真放不下时去收 `.cover` 的高度（那条 `min(36dvh, 88vw)`），别回来夹宽度。
   大图的 `.bd-body` 用 `object-fit:fill` 而不是 `contain`：构造上保证对齐。
2. **帧图不能缩小。** 缩过一版（一半尺寸，总共 208 KB），补丁边界会显出一道浅色的缝——
   身体那张在活动区是透明的，缩图时边界像素会和透明邻居平均，而帧图是逐格裁出来缩的，
   两边的边缘算法对不上。现在**全部原生分辨率**，缝没了，代价是这几张合计 423 KB
   （都在 `sw.js` 的 SHELL_URLS 和 `main.py` 的 `_SHELL_FILES` 里，第二次启动 0 网络）。

## 没有颜色跟随了

v2 的 README 明说「颜料点保留原来的颜色和位置，**本包不包含用于动态染色的 body/paint 分层**」。
上一版是我自己从原图里抠颜料再用 CSS mask 染色，用户看线上第一眼就是「精灵脸上的颜料有点问题」。
所以现在颜料是原色，**不跟孩子的画变**。

「颜色跟着你的画走」这条线现在只剩**身后那圈光**（`renderWorld()` 里的 `--glow` / `--glow-a`），
九维进度那套数据一个字段没动。要把染色做回来，需要一份**干净的 body（无颜料）+ 颜料剪影**，
不是再抠一次。

图加载不出来时 `onerror` 把容器标成 `data-noart`，CSS 换回 `spriteInner()` 的 SVG 线稿——
和 families/badges「有图用图、没图用线稿」一个路子，**那条兜底别删**。

## 六个形象（2026-10-04 起）

上面说的是 `normal`。另外五个在各自的子目录里，由 **`tools/build_buddy_roles.py`** 从 `docs/`
里用户给的素材出（换素材重跑一次，它会打印要抄进 style.css 的百分比）：

| 角色 | 用在哪 | 动不动 | 素材来源 |
| --- | --- | --- | --- |
| `explore/` | 地图右边那张任务卡底下（`.t-sprite`，160px）；节点上不再站精灵 | 眨眼 + 双脚 + 两只手小幅转（`eyes/feet/rest/mag` 四张贴片） | `docs/04_explore_complete.zip`（有分层） |
| `reading/` | 任务说明页「想画什么？」右边（`#intent-sprite`） | 只眨眼 | `docs/demo_standalone.html`（05 的分层内嵌在 HTML 里） |
| `thinking/` | 求助请求**真的发出去之后**的窗头像；提交后的等待层 `#overlay` | 静态 | `docs/03_thinking.png` |
| `happy/` | 提交并保存成功后的下一屏播一次（3 秒），然后停在静态图 | 单次 | `docs/02_happy_painter_transparent.webp`（烤死的动图，取 30 帧） |
| `encourage/` | 问卷头、结算页改过之后的那张卡 | 静态 | `docs/06_橙帽眨眼抱心萌球.png` |

每个目录：`body.webp` 整只 480 宽、`icon.webp` 256 头部特写（给 26–40px 的小头像位）；
会眨眼的多一张 `eyes.webp`（9 帧）；happy 多一张 `cheer.webp`（6×5 格，走 `bd-limb` 同一张表）。
**它们不进外壳**（sw.js / main.py 的清单只有 normal 那四张）：地图一出来拉 explore，写心愿时预取
thinking / happy / encourage（`buddyPrefetch`），第一次切过去不留空档。

explore 的手脚是把包里的分层（身体 / 放大镜手 / 另一只手 / 脚的 60 帧）按 rig.json 的轴和角度
**在原生尺寸上合成 30 张整图**，再缩、再裁出四块贴片——所以不靠 CSS rotate，也不挖空。
层序 rest（身体后面）→ body → feet → eyes → mag（最上面），`BUDDY_ROLES.explore.parts` 的顺序就是它。

### 眨眼贴片为什么不挖空

normal 那套是身体挖洞 + 帧图填洞，所以帧图**不能缩**（上面第 2 个坑）。新形象反过来：
`body.webp` 是整只完整的图，`eyes.webp` 的第 0 帧就是从**同一次缩放**出来的整图上裁的那块，
贴上去像素一样（脚本里有 assert），闭眼帧盖上去也只换眼睛。所以缩到 26px 也不露缝。
贴片按 `.bd-fig`（1312:1199 的框，在 `.sprite` 方框里竖向居中）的百分比定位，
**百分比是脚本算的，别手改。**

### 三种模式（`style.css` 彩点那段）

- **日常陪伴**：帧图照常走。一屏最多一只在动：`.sprite.still` 的那只停在第 0 帧。
- **安静**：`body.painting`——`beginStroke` 加、最后一笔后 2 秒摘（`buddyQuiet`），
  所有帧图 `animation:none` + 停回第 0 帧。**不是 `paused`**：paused 会停在半闭眼上。
- **单次回应**：`buddyCheer(el, then, reason)` 往 `.bd-fig` 里塞 `.bd-cheer` 帧图，`.cheering` 把
  静态图藏起来，3 秒后摘掉、换回 `then` 那个形象。**只有 `state.cheerPending` 点亮才播**
  （两处 submit 成功后），`paintOrCheer()` 消费它——自动保存、重试、重进页面都碰不到。
  `show()` 切屏时收掉不在新屏上的庆祝；页面不可见（`body.page-hidden`）直接收掉，回来不补播。

每次换形象记一条 `MASCOT_STATE`（role / mode / reason / view / asset_v），见 `artquest/events.py`。
安静模式进出不记——从 stroke 流能一字不差算回来。

## 还缺

`icon-happy.webp` 现在是 `icon.webp` 的副本，已经没人用它（happy 有自己的目录）；留着是怕旧缓存里的
页面还引用。下次 bump 外壳版本时可以删。
