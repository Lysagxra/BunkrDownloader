import Foundation

enum LinkParser {
    static func normalize(_ raw: String) -> String? {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty,
              var c = URLComponents(string: text.contains("://") ? text : "https://" + text),
              c.scheme?.lowercased() == "https", c.user == nil, c.password == nil, c.port == nil,
              let host = c.host?.lowercased(),
              host.range(of: #"^(www\.)?bunkrr?\.[a-z]{2,}$"#, options: .regularExpression) != nil,
              c.percentEncodedPath.range(of: #"^/(?:a/[A-Za-z0-9_-]+|[fiv]/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)/?$"#, options: .regularExpression) != nil
        else { return nil }
        c.scheme = "https"; c.host = host; c.query = nil; c.fragment = nil
        if c.path.hasSuffix("/") { c.path.removeLast() }
        return c.string
    }
}
