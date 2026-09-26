import SwiftUI
import UIKit
import WebKit

/// 全 app 只有一个 WKWebView；App.swift 在退后台时要找到它推一把队列。
final class WebHost {
    static let shared = WebHost()
    weak var webView: WKWebView?
    func evaluate(_ js: String) {
        DispatchQueue.main.async { self.webView?.evaluateJavaScript(js, completionHandler: nil) }
    }
}

struct WebView: UIViewRepresentable {
    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.setURLSchemeHandler(BundleSchemeHandler(), forURLScheme: BundleSchemeHandler.scheme)
        config.websiteDataStore = .default()               // localStorage / IndexedDB 要持久
        config.allowsInlineMediaPlayback = true
        config.preferences.javaScriptCanOpenWindowsAutomatically = false
        // 页面开始之前先把「我在 app 里」这件事告诉 JS：服务器在哪、令牌是什么、我是哪一版。
        // app.js / log.js 开头读 window.ArtQuestNative 决定所有地址；没有它就是网页版。
        config.userContentController.addUserScript(WKUserScript(
            source: Coordinator.bootScript(), injectionTime: .atDocumentStart, forMainFrameOnly: true))
        config.userContentController.add(context.coordinator, name: Bridge.handlerName)

        let web = WKWebView(frame: .zero, configuration: config)
        web.uiDelegate = context.coordinator
        web.navigationDelegate = context.coordinator
        web.isOpaque = false
        web.backgroundColor = .white
        web.scrollView.backgroundColor = .white
        // 外壳自己是一个 100dvh 的 app 布局：外层不许弹、不许让系统再加安全区内边距
        web.scrollView.bounces = false
        web.scrollView.contentInsetAdjustmentBehavior = .never
        web.scrollView.isScrollEnabled = true
        web.allowsBackForwardNavigationGestures = false
        web.allowsLinkPreview = false
        #if DEBUG
        if #available(iOS 16.4, *) { web.isInspectable = true }   // Mac 上的 Safari → 开发 → 这台 iPad
        #endif
        // Apple Pencil 双击（系统设置里孩子选的那个动作我们不管，一律当「切橡皮」）
        let pencil = UIPencilInteraction()
        pencil.delegate = context.coordinator
        web.addInteraction(pencil)

        WebHost.shared.webView = web
        web.load(URLRequest(url: BundleSchemeHandler.startURL))
        return web
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKScriptMessageHandler, WKUIDelegate, WKNavigationDelegate,
                             UIPencilInteractionDelegate {
        static func bootScript() -> String {
            // 用 JSON 序列化，令牌和地址里不管有什么字符都进不了 JS 语法
            let payload: [String: Any] = ["platform": "ios", "server": AppConfig.serverOrigin,
                                          "token": Keychain.token, "version": AppConfig.version]
            let json = (try? JSONSerialization.data(withJSONObject: payload)).flatMap { String(data: $0, encoding: .utf8) } ?? "{}"
            return "window.ArtQuestNative = \(json);"
        }

        // -- JS → Swift -----------------------------------------------------
        func userContentController(_ c: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == Bridge.handlerName, let body = message.body as? [String: Any] else { return }
            Bridge.handle(body, from: message.webView)
        }

        // -- alert / confirm / prompt：WKWebView 默认把它们**吞掉**，页面里退出登录那句确认就会哑 --
        func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
            let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            a.addAction(UIAlertAction(title: "好", style: .default) { _ in completionHandler() })
            Bridge.present(a, over: webView)
        }

        func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
            let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            a.addAction(UIAlertAction(title: "算了", style: .cancel) { _ in completionHandler(false) })
            a.addAction(UIAlertAction(title: "好", style: .default) { _ in completionHandler(true) })
            Bridge.present(a, over: webView)
        }

        func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String,
                     defaultText: String?, initiatedByFrame frame: WKFrameInfo,
                     completionHandler: @escaping (String?) -> Void) {
            let a = UIAlertController(title: nil, message: prompt, preferredStyle: .alert)
            a.addTextField { $0.text = defaultText }
            a.addAction(UIAlertAction(title: "算了", style: .cancel) { _ in completionHandler(nil) })
            a.addAction(UIAlertAction(title: "好", style: .default) { _ in completionHandler(a.textFields?.first?.text) })
            Bridge.present(a, over: webView)
        }

        // -- 导航：外壳自己的地址留在壳里；任何 http(s) 链接（导出 JSON、target=_blank）交给 Safari --
        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = action.request.url else { return decisionHandler(.allow) }
            if url.scheme == BundleSchemeHandler.scheme || url.scheme == "about" || url.scheme == "blob" {
                return decisionHandler(.allow)
            }
            if ["http", "https", "mailto"].contains(url.scheme ?? "") {
                UIApplication.shared.open(url)
            }
            decisionHandler(.cancel)
        }

        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                     for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            if let url = action.request.url, ["http", "https"].contains(url.scheme ?? "") {
                UIApplication.shared.open(url)
            }
            return nil
        }

        // -- Apple Pencil 双击 → JS 事件；app.js 里监听 artquest:pencilTap 切橡皮 --
        func pencilInteractionDidTap(_ interaction: UIPencilInteraction) {
            guard UIPencilInteraction.preferredTapAction != .ignore else { return }
            WebHost.shared.evaluate("window.dispatchEvent(new Event('artquest:pencilTap'))")
        }
    }
}
