import Foundation

/// 这个壳连哪台服务器、自己是哪一版。
enum AppConfig {
    /// 系统「设置」里填的临时地址优先（测试的人指向 Tailscale 上的开发机），
    /// 其次是构建时写进 Info.plist 的正式地址（project.yml 里的 ARTQUEST_SERVER）。
    static var serverURL: URL {
        let typed = (UserDefaults.standard.string(forKey: "artquest_server") ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if let u = URL(string: typed), let scheme = u.scheme, ["http", "https"].contains(scheme), u.host != nil {
            return u
        }
        let built = (Bundle.main.object(forInfoDictionaryKey: "ARTQUEST_SERVER") as? String ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return URL(string: built.isEmpty ? "https://art.ddhulu.cn" : built)!
    }

    /// 不带末尾斜杠的源，JS 端拿它拼 `/api/v1/...` 和 `/files/...`。
    static var serverOrigin: String {
        var s = serverURL.absoluteString
        while s.hasSuffix("/") { s.removeLast() }
        return s
    }

    /// 「0.3.0 (1)」——写进 session 的 device.app.version，也显示在「我的 → 这台设备」。
    static var version: String {
        let short = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "?"
        let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "?"
        return "\(short) (\(build))"
    }
}
