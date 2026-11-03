import XCTest
import Foundation

private let corpusURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().appending(path: "fixtures/resolver.json")

private final class ServiceFixture: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        let url = request.url!
        let body: String
        var status = 200
        var mime = "text/html"
        let corpus = try! JSONSerialization.jsonObject(with: Data(contentsOf: corpusURL)) as! [String: Any]
        let pages = corpus["pages"] as! [String: String]
        if let html = pages[url.absoluteString] {
            let bytes = Data(html.utf8)
            client?.urlProtocol(self, didReceive: HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "text/html"])!, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: bytes)
            client?.urlProtocolDidFinishLoading(self)
            return
        }
        switch url.host {
        case "bunkr.cr":
            switch url.path {
            case "/a/demo":
                if url.query == nil {
                    body = #"<a class="after:inset-0" href="/i/first">One</a><nav class="pagination"><a href="?page=2">Next</a></nav>"#
                } else {
                    body = #"<a class="after:inset-0" href="/i/first">Repeated</a><a class="after:inset-0" href="/f/second.bin">Two</a>"#
                }
            case "/a/partial":
                body = #"<a class="after:inset-0" href="/i/first"></a><a class="after:inset-0" href="/v/error"></a><a class="after:inset-0" href="/f/second.bin"></a>"#
            case "/v/error":
                body = #"<script>var jsCDN = "https://fixtures.test/error";</script>"#
            case "/f/second.bin":
                body = #"<script data-file-id="42"></script><h1>../same.bin</h1>"#
            default:
                body = #"<script>var jsCDN = "https:\/\/fixtures.test\/first";</script><h1>../same.bin</h1>"#
            }
        case "dl.bunkr.cr" where request.httpMethod == "POST":
            mime = "application/json"
            var payload = request.httpBody ?? Data()
            if let stream = request.httpBodyStream {
                stream.open()
                defer { stream.close() }
                var buffer = [UInt8](repeating: 0, count: 1024)
                while stream.hasBytesAvailable {
                    let count = stream.read(&buffer, maxLength: buffer.count)
                    if count <= 0 { break }
                    payload.append(contentsOf: buffer.prefix(count))
                }
            }
            body = String(decoding: payload, as: UTF8.self).contains("corpus-two")
                ? #"{"mediafiles":"https://fixtures.test","path":"/two.bin"}"#
                : #"{"mediafiles":"https://fixtures.test","path":"/second.bin"}"#
        case "glb-apisign.cdn.cr":
            mime = "application/json"
            let paths = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems
            body = #"{"token":"signed","ex":1234}"#
            if !["/first", "/storage/media/second.bin", "/error", "/one.bin", "/storage/media/two.bin"].contains(paths?.first?.value ?? "") { status = 400 }
        case "fixtures.test":
            mime = "application/octet-stream"
            body = url.lastPathComponent
            if url.path == "/error" { mime = "text/html" }
            if url.query != "token=signed&ex=1234" || request.value(forHTTPHeaderField: "Referer") != "https://dl.bunkrr.cr/" { status = 403 }
        default:
            body = "Unavailable"
            status = 404
        }
        let bytes = Data(body.utf8)
        let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1",
                                       headerFields: ["Content-Type": mime, "Content-Length": String(bytes.count)])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: bytes)
        client?.urlProtocolDidFinishLoading(self)
    }
}

final class TransferTests: XCTestCase {
    func testInsufficientStorageDoesNotPublishFile() async throws {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [ServiceFixture.self]
        let session = URLSession(configuration: config)
        defer { session.invalidateAndCancel() }
        let folder = URL.temporaryDirectory.appending(path: UUID().uuidString)
        do {
            _ = try await TransferService(session: session, availableCapacity: { _ in 0 })
                .download(URL(string: "https://bunkr.cr/i/first")!, into: folder, wifiOnly: true)
            XCTFail("Expected a storage failure")
        } catch let error as TransferError { XCTAssertTrue(error.message.contains("Free up at least")) }
        XCTAssertFalse(FileManager.default.fileExists(atPath: folder.path))
    }

    @MainActor func testAlbumContinuesAndRetriesOnlyFailedItems() async throws {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [ServiceFixture.self]
        let session = URLSession(configuration: config)
        defer { session.invalidateAndCancel() }
        let folder = URL.temporaryDirectory.appending(path: UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let queue = MobileQueue(state: folder.appending(path: "queue.json"), documents: folder.appending(path: "Documents"), service: TransferService(session: session))
        queue.wifiOnly = true
        XCTAssertTrue(queue.add("https://bunkr.cr/a/partial"))
        queue.wifiOnly = false
        XCTAssertEqual(queue.jobs.first?.wifiOnly, true)
        queue.start()
        for _ in 0..<500 where queue.active { try await Task.sleep(for: .milliseconds(10)) }
        let job = try XCTUnwrap(queue.jobs.first)
        XCTAssertEqual(job.status, .failed)
        XCTAssertEqual(job.files.count, 2)
        XCTAssertEqual(job.failures?.count, 1)
        let files = folder.appending(path: "Documents").appending(path: job.folderName)
        let before = try FileManager.default.contentsOfDirectory(atPath: files.path).sorted()
        queue.retry(job.id)
        for _ in 0..<500 where queue.active { try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: files.path).sorted(), before)
        XCTAssertEqual(queue.jobs.first?.failures?.count, 1)
    }

    func testSharedResolverCorpus() async throws {
        let corpus = try JSONSerialization.jsonObject(with: Data(contentsOf: corpusURL)) as! [String: Any]
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [ServiceFixture.self]
        let session = URLSession(configuration: config)
        defer { session.invalidateAndCancel() }
        let service = TransferService(session: session)
        let items = try await service.items(for: URL(string: corpus["album"] as! String)!)
        XCTAssertEqual(items.map(\.absoluteString), corpus["items"] as? [String])
        for (item, expected) in zip(items, corpus["expected"] as! [[String: String]]) {
            let media = try await service.resolve(item)
            XCTAssertEqual(media.name, expected["name"])
            XCTAssertEqual(media.url.absoluteString, expected["base"]! + "?token=signed&ex=1234")
        }
        for path in ["missing", "challenge"] {
            do {
                _ = try await service.resolve(URL(string: "https://bunkr.cr/f/" + path)!)
                XCTFail("Unavailable items must fail resolution")
            } catch is TransferError { }
        }
    }

    @MainActor func testAlbumFromInputToFilesAndRestoredHistory() async throws {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [ServiceFixture.self]
        let session = URLSession(configuration: config)
        defer { session.invalidateAndCancel() }
        let folder = URL.temporaryDirectory.appending(path: UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let state = folder.appending(path: "state.json")
        let docs = folder.appending(path: "Documents")
        let queue = MobileQueue(state: state, documents: docs, service: TransferService(session: session))
        XCTAssertFalse(queue.add("https://example.org/f/x"))
        XCTAssertTrue(queue.add("bunkr.cr/a/demo\nhttps://bunkr.cr/a/demo/?page=2"))
        XCTAssertEqual(queue.jobs.count, 1)
        queue.start()
        for _ in 0..<500 where queue.active { try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertFalse(queue.active)
        let restored = MobileQueue(state: state, documents: docs)
        let job = try XCTUnwrap(restored.jobs.first)
        XCTAssertEqual(job.status, .finished, job.detail)
        XCTAssertEqual(job.total, 2)
        XCTAssertEqual(Set(job.files.values).count, 2)
        for (key, name) in job.files {
            XCTAssertFalse(name.contains("/"))
            let output = docs.appending(path: job.folderName).appending(path: name)
            XCTAssertEqual(try String(contentsOf: output, encoding: .utf8), URL(string: key)?.lastPathComponent)
        }
        XCTAssertEqual(job.files.count, 2)
        restored.remove(job.id)
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: docs.appending(path: job.folderName).path).count, 2)
    }

    func testErrorPageDoesNotBecomeAFile() async throws {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [ServiceFixture.self]
        let session = URLSession(configuration: config)
        defer { session.invalidateAndCancel() }
        let folder = URL.temporaryDirectory.appending(path: UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        do {
            _ = try await TransferService(session: session).download(URL(string: "https://bunkr.cr/v/error")!, into: folder)
            XCTFail("A successful HTTP status with an HTML body must not publish a file.")
        } catch let error as TransferError {
            XCTAssertTrue(error.message.contains("error page"))
        }
        XCTAssertFalse(FileManager.default.fileExists(atPath: folder.path))
    }

    @MainActor func testInterruptedJobNeedsExplicitRetry() async throws {
        let folder = URL.temporaryDirectory.appending(path: UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let state = folder.appending(path: "queue.json")
        var job = MobileJob(link: URL(string: "https://bunkr.cr/i/first")!)
        job.status = .running
        job.files[job.link.absoluteString] = "saved.bin"
        try JSONEncoder().encode([job]).write(to: state)
        let docs = folder.appending(path: "Documents")
        let jobFolder = docs.appending(path: job.folderName)
        try FileManager.default.createDirectory(at: jobFolder, withIntermediateDirectories: true)
        let original = Data("previously completed bytes".utf8)
        let saved = jobFolder.appending(path: "saved.bin")
        try original.write(to: saved)

        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [ServiceFixture.self]
        let session = URLSession(configuration: config)
        defer { session.invalidateAndCancel() }
        let queue = MobileQueue(state: state, documents: docs, service: TransferService(session: session))
        XCTAssertFalse(queue.active)
        XCTAssertEqual(queue.jobs.first?.status, .stopped)
        XCTAssertEqual(queue.jobs.first?.files, job.files)
        queue.retry(job.id)
        for _ in 0..<500 where queue.active { try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertEqual(queue.jobs.first?.status, .finished)
        XCTAssertEqual(try Data(contentsOf: saved), original)
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: jobFolder.path), ["saved.bin"])
    }
}
