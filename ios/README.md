# KidsArtQuest · iOS

这个目录是 iOS app 的全部原生代码。**界面不在这里**——界面是仓库根下的 `static/`，
和网页版是同一份，整个目录以文件夹引用的方式打进 app 包，运行时从 `artquest://app/` 端出去。
所以改网页版就是改 app；这里的 Swift 只做网页做不到的事。

## 它是什么、不是什么

| | 网页版（浏览器 / 装到主屏） | iOS app |
|---|---|---|
| 界面 | `static/` | 同一份 `static/`，打在包里，**断网也开得起来** |
| API | 同源 `/api/v1` | `https://art.ddhulu.cn/api/v1`（跨源，服务器 CORS 放行 `artquest://app`） |
| 登录令牌 | localStorage | **钥匙串**（删掉重装还在——「画跟着人走」在手机上就靠它） |
| Apple Pencil | 压感 / 倾角（WebKit 本来就给） | 同上 + **双击切橡皮** |
| 其他 | — | 点亮徽章震一下、结算页分享到相册 / AirDrop、画画时不锁屏、`alert/confirm` 走系统弹窗 |

**画画引擎故意留在 JS 里。** 服务端 `reconstruct.py` 要从笔画流逐像素重建作品、和 `final.png`
对账（QC 阈值 0.30 是按浏览器 Canvas 标定的）。换一个渲染器就得重新标定整条 replay 契约，
而那是全部研究数据的地基。哪天真要原生画布，这个壳的其余部分（鉴权、API、桥）原样能用。

## 构建

需要一台 Mac、Xcode 15+。`.xcodeproj` 不进仓库，由 [XcodeGen](https://github.com/yonaskolb/XcodeGen) 从 `project.yml` 生成：

```sh
brew install xcodegen
cd ios
xcodegen generate
open ArtQuest.xcodeproj
```

打开后在 *Signing & Capabilities* 里选自己的 Team（或把 Team ID 填进 `project.yml` 的 `DEVELOPMENT_TEAM`），
选一台 iPad 或模拟器，Run。

## 连哪台服务器

1. 正式地址写在 `project.yml` → `ARTQUEST_SERVER`（默认 `https://art.ddhulu.cn`），构建时进 `Info.plist`。
2. 装好之后，系统 **设置 → KidsArtQuest → 服务器地址** 可以临时改成别的（比如 Tailscale 上的开发机
   `https://<机器名>.<tailnet>.ts.net`），不用重新打包。留空回到正式地址。改完要重开 app。
3. 服务器那边要放行这个源：`ARTQUEST_CORS_ORIGINS` 默认已经含 `artquest://app`，不用动。

## 文件

| 文件 | 干什么 |
|---|---|
| `App.swift` | `@main`；退后台时让 JS 把没送出去的笔画推一把 |
| `WebView.swift` | 唯一的 WKWebView：注入 `window.ArtQuestNative`、接 JS 消息、系统弹窗、外链交给 Safari、Pencil 双击 |
| `BundleSchemeHandler.swift` | 把包里的 `static/` 当网站端出去（`artquest://app/`） |
| `Bridge.swift` | JS → Swift 的五件事：`token` `haptic` `keepAwake` `share` `open` |
| `Keychain.swift` | 令牌的家 |
| `AppConfig.swift` | 服务器地址、版本号 |
| `Info.plist` | 方向（iPhone 只竖屏、iPad 四向）、相册权限说明、本地网络放行 |
| `PrivacyInfo.xcprivacy` | 上架必填的隐私清单 |
| `Settings.bundle` | 系统设置里那一页（服务器地址） |
| `Assets.xcassets` | 图标（**现在是 512 拉到 1024 的占位**，等 `docs/ART_LIST.md` 里的正式图标） |

## JS 这边的约定

- 页面开始前壳注入 `window.ArtQuestNative = { platform: "ios", server, token, version }`。
  `app.js` / `log.js` 开头读它拼 `${server}/api/v1` 和 `${server}/files`；没有它就是网页版。
- JS 调壳：`native(type, payload)` → `webkit.messageHandlers.artquest.postMessage({type, ...})`。
- 壳调 JS：`window.dispatchEvent(new Event("artquest:pencilTap"))`。
- Service Worker 在 `artquest://` 下**不注册**（app.js 里按协议判断），外壳本来就在包里，用不着它。

## 还没在真机上验过的

这台开发机是 Linux，Swift 没法编译，以上代码按 iOS 15 SDK 的公开接口写，**第一次在 Xcode 里编要有心理准备改几处**。
跨源那条链路（外壳在别的源、API 带 `Authorization`、CORS 预检）在 Chrome 里用第二个源真跑过
（`tests/test_app_api.py::TheShellRunsFromAnotherOrigin`）；WebKit 特有的几样——
`artquest://` 下 IndexedDB 是否持久、`crypto.randomUUID` 是否可用（有退路）、Pencil 双击回调——要上机看。
