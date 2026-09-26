import Foundation
import UniformTypeIdentifiers
import WebKit

/// 把 app 包里的 `static/` 目录当成一个网站端出去：`artquest://app/` 是首页，
/// `artquest://app/static/style.css` 是样式，和服务器上的路径一模一样——
/// 所以 index.html 里那些 `/static/...` 的绝对路径一个字不用改。
///
/// 只服务静态文件。`/api/...` 和 `/files/...` 不经过这里：JS 端拿 `ArtQuestNative.server`
/// 拼成绝对地址直接请求服务器（跨源，服务器那边用 CORS 放行 `artquest://app`）。
/// 不在这里代理 API 是有意的——WKURLSchemeHandler 拿 POST 请求体这件事各版本 iOS 表现不一，
/// 而孩子画的每一笔都是 POST。
final class BundleSchemeHandler: NSObject, WKURLSchemeHandler {
    static let scheme = "artquest"
    static let host = "app"
    static let startURL = URL(string: "\(scheme)://\(host)/")!

    private let root: URL = Bundle.main.resourceURL!.appendingPathComponent("static", isDirectory: true)
        .standardizedFileURL

    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        guard let url = task.request.url else { return fail(task, 400) }
        var path = url.path
        if path.isEmpty || path == "/" { path = "/index.html" }
        if path.hasPrefix("/static/") { path.removeFirst("/static".count) }
        let file = root.appendingPathComponent(path).standardizedFileURL
        // 路径穿越：解析完必须还在 static/ 里
        guard file.path.hasPrefix(root.path), let data = try? Data(contentsOf: file) else {
            return fail(task, 404)
        }
        let headers = ["Content-Type": mime(for: file), "Content-Length": String(data.count),
                       "Cache-Control": "no-cache"]
        guard let resp = HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: headers)
        else { return fail(task, 500) }
        task.didReceive(resp)
        task.didReceive(data)
        task.didFinish()
    }

    func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {}

    private func fail(_ task: WKURLSchemeTask, _ code: Int) {
        if let url = task.request.url,
           let resp = HTTPURLResponse(url: url, statusCode: code, httpVersion: "HTTP/1.1", headerFields: nil) {
            task.didReceive(resp)
            task.didFinish()
        } else {
            task.didFailWithError(URLError(.fileDoesNotExist))
        }
    }

    private func mime(for file: URL) -> String {
        // 系统不认的几种要自己写：字体和 manifest 给错类型，Safari 会拒绝加载
        switch file.pathExtension.lowercased() {
        case "js": return "application/javascript; charset=utf-8"
        case "html": return "text/html; charset=utf-8"
        case "css": return "text/css; charset=utf-8"
        case "json": return "application/json; charset=utf-8"
        case "webmanifest": return "application/manifest+json"
        case "woff2": return "font/woff2"
        case "woff": return "font/woff"
        case "svg": return "image/svg+xml"
        default:
            return UTType(filenameExtension: file.pathExtension)?.preferredMIMEType ?? "application/octet-stream"
        }
    }
}
