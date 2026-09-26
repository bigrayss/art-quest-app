// KidsArtQuest 的 iOS 壳。
//
// 这个 app 是什么、不是什么，一段话说清楚：
//
// **界面是同一套网页外壳（../static），打进 app 包里，跑在 WKWebView 里；Swift 只负责网页做不到的事。**
// 不是「浏览器套壳」——外壳不从服务器载入（断网也开得起来，首屏零等待），令牌住在钥匙串里
// （删掉重装还在，「画跟着人走」在手机上就靠它），Apple Pencil 双击、震动、分享面板、
// 画画时不锁屏，都是原生的。也不是「原生重写」——画画引擎故意留在 JS 里：
// 服务端 `reconstruct.py` 要从笔画流逐像素重建作品并和 final.png 对账（QC 阈值 0.30 是按
// Canvas 标定的），换一个渲染器就要重新标定整条 replay 契约，而它是全部研究数据的地基。
// 一份界面代码，网页版和 app 同时受益；哪天真要原生画布，这个壳的其余部分（鉴权、API、桥）原样能用。
import SwiftUI
import WebKit

@main
struct ArtQuestApp: App {
    @Environment(\.scenePhase) private var phase

    var body: some Scene {
        WindowGroup {
            ContentView()
                .ignoresSafeArea()          // 外壳自己按 env(safe-area-inset-*) 排版（viewport-fit=cover）
                .statusBarHidden(false)
        }
        .onChange(of: phase) { newPhase in
            // 退到后台前把还没送出去的笔画推一把。队列本来就在 IndexedDB 里，丢不了，
            // 这一下只是让「都收好啦」早一点成立。
            if newPhase != .active {
                WebHost.shared.evaluate("window.ArtLog && ArtLog.flush && ArtLog.flush()")
            }
            if newPhase == .background {
                UIApplication.shared.isIdleTimerDisabled = false   // 别把「画画时不锁屏」带到后台去
            }
        }
    }
}

struct ContentView: View {
    var body: some View {
        WebView()
            .background(Color.white)
    }
}
