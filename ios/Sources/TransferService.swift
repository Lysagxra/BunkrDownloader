import Foundation
import libxml2

struct TransferError: LocalizedError {
    let message: String
    init(_ message: String) { self.message = message }
    var errorDescription: String? { message }
}

private final class Page {
    private let document: htmlDocPtr

    init(_ data: Data) throws {
        guard !data.isEmpty, data.count <= Int32.max,
              let parsed = data.withUnsafeBytes({ bytes in
                  htmlReadMemory(bytes.bindMemory(to: CChar.self).baseAddress, Int32(bytes.count),
                                 nil, "UTF-8", Int32(HTML_PARSE_NONET.rawValue | HTML_PARSE_NOERROR.rawValue | HTML_PARSE_NOWARNING.rawValue))
              }) else { throw TransferError("The service returned an unreadable page.") }
        document = parsed
    }

    deinit { xmlFreeDoc(document) }

    func values(_ xpath: String) -> [String] {
        guard let context = xmlXPathNewContext(document) else { return [] }
        defer { xmlXPathFreeContext(context) }
        guard let result = xmlXPathEvalExpression(xpath, context) else { return [] }
        defer { xmlXPathFreeObject(result) }
        guard let nodes = result.pointee.nodesetval?.pointee, let table = nodes.nodeTab else { return [] }
        return (0..<Int(nodes.nodeNr)).compactMap { index in
            guard let value = xmlNodeGetContent(table[index]) else { return nil }
            defer { xmlFree(value) }
            return String(cString: value).trimmingCharacters(in: .whitespacesAndNewlines)
        }
    }
}

struct TransferService {
    static let defaultSession: URLSession = {
        let configuration = URLSessionConfiguration.default
        configuration.waitsForConnectivity = true
        return URLSession(configuration: configuration)
    }()
    var session: URLSession = Self.defaultSession
    var availableCapacity: (URL) throws -> Int64? = { folder in
        var volume = folder
        while !FileManager.default.fileExists(atPath: volume.path), volume.path != "/" { volume.deleteLastPathComponent() }
        return try volume.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey]).volumeAvailableCapacityForImportantUsage
    }
    private let signer = URL(string: "https://glb-apisign.cdn.cr/sign")!
    private let lookup = URL(string: "https://dl.bunkr.cr/api/_001_v2")!

    private func check(_ response: URLResponse) throws -> HTTPURLResponse {
        guard let http = response as? HTTPURLResponse, http.url?.scheme == "https",
              (200..<300).contains(http.statusCode) else {
            let status = (response as? HTTPURLResponse)?.statusCode
            throw TransferError(status.map { "The service returned HTTP \($0)." } ?? "Invalid service response.")
        }
        return http
    }

    private func data(_ request: URLRequest) async throws -> Data {
        let (bytes, response) = try await session.data(for: request)
        _ = try check(response)
        return bytes
    }

    func title(for link: URL) async throws -> String {
        let page = try await Page(data(URLRequest(url: link)))
        return page.values("//h1").first ?? page.values("//title").first ?? link.lastPathComponent
    }

    func items(for link: URL) async throws -> [URL] {
        guard link.path.hasPrefix("/a/") else { return [link] }
        var items: [URL] = []
        var seen = Set<URL>()
        var number = 1
        var last = 1
        while number <= last {
            let url = number == 1 ? link : link.appending(queryItems: [.init(name: "page", value: String(number))])
            let page = try await Page(data(URLRequest(url: url)))
            let itemLinks = "//a[contains(concat(' ',normalize-space(@class),' '),' after:inset-0 ')]/@href"
            let links = try page.values(itemLinks).map { href -> URL in
                guard let absolute = URL(string: href, relativeTo: link)?.absoluteURL,
                      let canonical = LinkParser.normalize(absolute.absoluteString),
                      let item = URL(string: canonical), !item.path.hasPrefix("/a/") else {
                    throw TransferError("Album page \(number) contains an unsupported file link.")
                }
                return item
            }
            guard !links.isEmpty else { throw TransferError("No downloadable files found on album page \(number).") }
            items.append(contentsOf: links.filter { seen.insert($0).inserted })
            let pages = page.values("//nav[contains(concat(' ',normalize-space(@class),' '),' pagination ')]//a/@href")
            for href in pages {
                let query = URLComponents(string: href)?.queryItems
                if let value = query?.first(where: { $0.name == "page" })?.value, let n = Int(value) {
                    guard n <= 1000 else { throw TransferError("Album pagination exceeds 1,000 pages.") }
                    last = max(last, n)
                }
            }
            number += 1
        }
        return items
    }

    private func mediaURL(_ text: String) throws -> URL {
        guard let url = URL(string: text), url.scheme == "https", url.host != nil,
              url.user == nil, url.password == nil else { throw TransferError("Invalid media URL.") }
        return url
    }

    func resolve(_ item: URL) async throws -> (url: URL, name: String) {
        let page = try await Page(data(URLRequest(url: item)))
        let scripts = page.values("//script/text()").joined(separator: "\n")
        let pattern = #/\bvar\s+jsCDN\s*=\s*["']([^"']+)["']/#
        let base: URL
        let path: String
        let cdn = scripts.firstMatch(of: pattern)
        if let cdn {
            // Decode JavaScript URL escapes such as \/ and \u002F.
            let literal = Data(("\"" + String(cdn.1) + "\"").utf8)
            base = try mediaURL(JSONDecoder().decode(String.self, from: literal))
            path = base.path(percentEncoded: true)
        } else {
            guard let id = page.values("//script/@data-file-id").first else { throw TransferError("No media found on the item page.") }
            var request = URLRequest(url: lookup)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(["id": id])
            struct Lookup: Decodable {
                let mediafiles: String
                let path: String
            }
            let info = try await JSONDecoder().decode(Lookup.self, from: data(request))
            guard var parts = URLComponents(url: try mediaURL(info.mediafiles), resolvingAgainstBaseURL: false),
                  info.path.hasPrefix("/"), let encoded = URLComponents(string: info.path)?.percentEncodedPath else {
                throw TransferError("Invalid media path.")
            }
            parts.percentEncodedPath = encoded
            guard let url = parts.url else { throw TransferError("Invalid media path.") }
            base = url
            path = "/storage/media/" + url.lastPathComponent
        }

        let signingURL = signer.appending(queryItems: [.init(name: "path", value: path)])
        let json = try await JSONSerialization.jsonObject(with: data(URLRequest(url: signingURL)))
        guard let fields = json as? [String: Any] else { throw TransferError("Invalid signing response.") }
        let name = page.values("//h1").first ?? base.lastPathComponent
        if let token = fields["token"] as? String, !token.isEmpty,
           let expiry = fields["ex"] as? String ?? (fields["ex"] as? NSNumber)?.stringValue, !expiry.isEmpty {
            return (base.appending(queryItems: [.init(name: "token", value: token), .init(name: "ex", value: expiry)]), name)
        }
        guard cdn != nil else { throw TransferError("The service did not sign this file.") }
        return (base, name)
    }

    func download(_ item: URL, into folder: URL, wifiOnly: Bool = false,
                  progress: ((Int64, Int64) -> Void)? = nil) async throws -> String {
        #if os(iOS)
        let transferKey = folder.lastPathComponent + "|" + item.absoluteString
        if let existing = try await BackgroundTransfers.shared.recover(key: transferKey) { return existing.lastPathComponent }
        #endif
        let media = try await resolve(item)
        var request = URLRequest(url: media.url)
        request.setValue("https://dl.bunkrr.cr/", forHTTPHeaderField: "Referer")
        request.allowsCellularAccess = !wifiOnly
        var head = request
        head.httpMethod = "HEAD"
        let (_, metadata) = try await session.data(for: head)
        if metadata.expectedContentLength > 0 {
            if let available = try availableCapacity(folder),
               available < metadata.expectedContentLength {
                throw TransferError("Free up at least \(ByteCountFormatter.string(fromByteCount: metadata.expectedContentLength - available, countStyle: .file)) to download this file.")
            }
        }
        #if os(iOS)
        let stableName = Self.filename(item.lastPathComponent + "-" + media.name, fallback: item.lastPathComponent)
        let destination = folder.appending(path: stableName)
        let key = folder.lastPathComponent + "|" + item.absoluteString
        await MainActor.run {
            BackgroundTransfers.shared.progress = { eventKey, received, expected in
                if eventKey == key { progress?(received, expected) }
            }
        }
        do {
            let output = try await BackgroundTransfers.shared.download(request, key: key, destination: destination)
            return output.lastPathComponent
        } catch {
            try Task.checkCancellation()
            // A signed URL may expire while waiting for connectivity. Resolve again once.
            let refreshed = try await resolve(item)
            request.url = refreshed.url
            let output = try await BackgroundTransfers.shared.download(request, key: key, destination: destination)
            return output.lastPathComponent
        }
        #else
        let (temporary, response) = try await session.download(for: request)
        defer { try? FileManager.default.removeItem(at: temporary) }
        let http = try check(response)
        guard http.statusCode == 200, http.mimeType != "text/html",
              http.mimeType != "application/json" else { throw TransferError("The service returned an error page or incomplete media.") }
        let size = try temporary.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
        guard size > 0 else { throw TransferError("The downloaded file was empty.") }
        if http.value(forHTTPHeaderField: "Content-Encoding") == nil, http.expectedContentLength >= 0,
           Int64(size) != http.expectedContentLength { throw TransferError("The file ended before its declared size.") }
        try Task.checkCancellation()
        if (try? folder.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == true {
            throw TransferError("The download folder was replaced by a link.")
        }
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let name = Self.filename(media.name, fallback: item.lastPathComponent)
        var target = folder.appendingPathComponent(name)
        var suffix = 2
        while FileManager.default.fileExists(atPath: target.path) {
            let original = name as NSString
            let ext = original.pathExtension
            let candidate = "\(original.deletingPathExtension) (\(suffix))" + (ext.isEmpty ? "" : "." + ext)
            target = folder.appendingPathComponent(candidate)
            suffix += 1
        }
        try FileManager.default.moveItem(at: temporary, to: target)
        progress?(Int64(size), http.expectedContentLength)
        return target.lastPathComponent
        #endif
    }

    static func filename(_ raw: String, fallback: String) -> String {
        let unsafe = CharacterSet.controlCharacters.union(CharacterSet(charactersIn: "/\\:"))
        var result = raw.components(separatedBy: unsafe).joined(separator: "_")
            .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: ".")))
        while result.utf8.count > 220 { result.removeLast() }
        return result.isEmpty ? String(fallback.prefix(120)) : result
    }
}
