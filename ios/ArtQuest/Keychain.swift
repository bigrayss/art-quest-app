import Foundation
import Security

/// 登录令牌的家。为什么不是 localStorage：WKWebView 的网站数据跟着 app 的沙盒走，
/// 删掉重装就没了；而账号存在的全部意义就是「换台设备、清了缓存，画还认得你」。
/// 钥匙串项在重装后仍在（不进 iCloud 同步——令牌是这一台设备的登录态，见 accounts.py 的 logout）。
enum Keychain {
    private static let service = "cn.ddhulu.kidsartquest"
    private static let account = "session-token"

    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service,
         kSecAttrAccount as String: account]
    }

    static var token: String {
        get {
            var q = query
            q[kSecReturnData as String] = true
            q[kSecMatchLimit as String] = kSecMatchLimitOne
            var out: CFTypeRef?
            guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess,
                  let data = out as? Data else { return "" }
            return String(data: data, encoding: .utf8) ?? ""
        }
        set {
            SecItemDelete(query as CFDictionary)
            guard !newValue.isEmpty, let data = newValue.data(using: .utf8) else { return }
            var q = query
            q[kSecValueData as String] = data
            // 解锁过一次之后就能读：app 在后台补传笔画时也拿得到
            q[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
            SecItemAdd(q as CFDictionary, nil)
        }
    }
}
