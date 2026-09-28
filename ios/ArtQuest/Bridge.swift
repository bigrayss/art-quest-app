import Photos
import UIKit
import WebKit

/// JS → Swift 的那几件事。JS 端只有一个入口 `native(type, payload)`（app.js 开头），
/// 消息形状 `{type, ...}`。列表刻意很短：网页做得到的就留在网页里。
enum Bridge {
    static let handlerName = "artquest"

    static func handle(_ msg: [String: Any], from webView: WKWebView?) {
        switch msg["type"] as? String ?? "" {
        case "token":
            // 登录 / 退出：令牌的正本进钥匙串。空串 = 退出（只退这台设备，见 accounts.py）
            Keychain.token = msg["value"] as? String ?? ""
        case "haptic":
            haptic(msg["style"] as? String ?? "light")
        case "keepAwake":
            // 画画的时候屏幕别自己暗下去；离开创作屏就恢复系统默认
            UIApplication.shared.isIdleTimerDisabled = (msg["on"] as? Bool) ?? false
        case "save":
            // 结算页的「存进相册」：一颗钮一件事，不弹系统分享面板（孩子看不懂那一排图标）
            save(dataURL: msg["image"] as? String ?? "", webView: webView)
        case "share":
            share(dataURL: msg["image"] as? String ?? "", title: msg["title"] as? String ?? "", over: webView)
        case "open":
            if let s = msg["url"] as? String, let u = URL(string: s), ["http", "https"].contains(u.scheme ?? "") {
                UIApplication.shared.open(u)
            }
        default:
            break
        }
    }

    private static func haptic(_ style: String) {
        switch style {
        case "success":
            let g = UINotificationFeedbackGenerator(); g.prepare(); g.notificationOccurred(.success)
        case "warning":
            let g = UINotificationFeedbackGenerator(); g.prepare(); g.notificationOccurred(.warning)
        default:
            let g = UIImpactFeedbackGenerator(style: .light); g.prepare(); g.impactOccurred()
        }
    }

    /// 把画直接写进相册。只申请「仅添加」这一档权限——我们从不读孩子的相册。
    /// 存完（或失败）通过 `artquest:saved` 事件告诉页面，按钮据此改字。
    private static func save(dataURL: String, webView: WKWebView?) {
        func report(_ ok: Bool, _ reason: String = "") {
            let js = "window.dispatchEvent(new CustomEvent('artquest:saved', {detail: {ok: \(ok), reason: '\(reason)'}}))"
            WebHost.shared.evaluate(js)
        }
        guard let comma = dataURL.firstIndex(of: ","),
              let data = Data(base64Encoded: String(dataURL[dataURL.index(after: comma)...])),
              let image = UIImage(data: data) else { return report(false, "decode") }
        PHPhotoLibrary.requestAuthorization(for: .addOnly) { status in
            guard status == .authorized || status == .limited else { return report(false, "denied") }
            PHPhotoLibrary.shared().performChanges({
                PHAssetChangeRequest.creationRequestForAsset(from: image)
            }) { ok, error in
                report(ok, error.map { String(describing: $0) } ?? "")
            }
        }
    }

    /// 系统分享面板（AirDrop / 发给家长）。界面上现在没有入口，桥留着，将来家长端可能要。
    /// 图片从 JS 的 data URL 里解出来——画就在 WebView 的画布上，不用再去服务器取一遍。
    private static func share(dataURL: String, title: String, over webView: WKWebView?) {
        guard let comma = dataURL.firstIndex(of: ","),
              let data = Data(base64Encoded: String(dataURL[dataURL.index(after: comma)...])),
              let image = UIImage(data: data) else { return }
        let vc = UIActivityViewController(activityItems: [image, title], applicationActivities: nil)
        vc.excludedActivityTypes = [.assignToContact, .print, .addToReadingList, .openInIBooks]
        if let pop = vc.popoverPresentationController, let v = webView {
            // iPad 上分享面板是气泡，必须给个锚点；锚在画布区中间就好
            pop.sourceView = v
            pop.sourceRect = CGRect(x: v.bounds.midX, y: v.bounds.midY, width: 1, height: 1)
            pop.permittedArrowDirections = []
        }
        present(vc, over: webView)
    }

    /// 在 WebView 所在的窗口最上层弹一个控制器（alert / 分享面板）。
    static func present(_ vc: UIViewController, over webView: WKWebView?) {
        DispatchQueue.main.async {
            // `UIWindowScene.keyWindow` 要 iOS 15 SDK；这样写 iOS 13 起都认，老 Xcode 也能编
            let keyWindow = UIApplication.shared.connectedScenes
                .compactMap { $0 as? UIWindowScene }
                .flatMap { $0.windows }
                .first { $0.isKeyWindow }
            guard var top = (webView?.window ?? keyWindow)?.rootViewController
            else { return }
            while let next = top.presentedViewController { top = next }
            top.present(vc, animated: true)
        }
    }
}
