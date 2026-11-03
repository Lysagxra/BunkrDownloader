import Foundation
#if !STANDALONE
import XCTest
@testable import Bunkr
#endif

final class BunkrTests: XCTestCase {
    func testDiagnosticRotationAndRedaction() throws {
        let root = URL.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let log = root.appendingPathComponent("engine.log")
        for _ in 0..<130 {
            DiagnosticLog.append(String(repeating: "x", count: 10_000), to: log)
        }
        DiagnosticLog.append("https://example.org/media?token=secret&ex=123&signature=private", to: log)
        let output = try String(contentsOf: log, encoding: .utf8)
        XCTAssertTrue(!output.contains("secret") && !output.contains("private") && !output.contains("ex=123"))
        XCTAssertTrue(try Data(contentsOf: log).count <= DiagnosticLog.limit)
        XCTAssertTrue(try Data(contentsOf: log.appendingPathExtension("1")).count <= DiagnosticLog.limit)
    }

    func testValidURLs() {
        XCTAssertEqual(LinkParser.normalize("bunkr.cr/f/archive-001.tar.gz"), "https://bunkr.cr/f/archive-001.tar.gz")
        XCTAssertEqual(LinkParser.normalize(" bunkr.si/a/abc/?page=2 "), "https://bunkr.si/a/abc")
        XCTAssertEqual(LinkParser.normalize("https://bunkrr.cr/f/File_1"), "https://bunkrr.cr/f/File_1")
    }
    func testInvalidURLs() {
        for link in ["", "file:///tmp/a", "https://bunkr.cr.evil.com/f/x", "https://bunkr.cr/a/..", "https://bunkr.cr/a/a%2Fb", "https://user@bunkr.cr/f/x", "http://bunkr.cr/f/x", "https://bunkr.cr:80/f/x"] {
            XCTAssertNil(LinkParser.normalize(link), link)
        }
    }
    @MainActor func testQueuePersistsAndInterruptedJobNeedsRetry() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let store = DownloadStore(support: folder)
        XCTAssertTrue(store.add("bunkr.cr/a/test\nbunkr.cr/a/test"))
        XCTAssertEqual(store.jobs.count, 1)
        store.jobs[0].status = .running
        store.save()
        let restored = DownloadStore(support: folder)
        XCTAssertEqual(restored.jobs[0].status, .cancelled)
        restored.retry(restored.jobs[0].id)
        XCTAssertEqual(restored.jobs[0].status, .queued)
    }
    @MainActor func testCorruptQueueIsPreserved() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let path = folder.appendingPathComponent("queue.json")
        try Data("broken".utf8).write(to: path)
        let store = DownloadStore(support: folder)
        XCTAssertNotNil(store.error)
        _ = store.add("bunkr.cr/a/test")
        let contents = try String(contentsOf: path, encoding: .utf8)
        XCTAssertEqual(contents, "broken")
    }
    func testRequestFiltersRemoveEmptyEntries() throws {
        var options = DownloadOptions()
        options.include = [" .mp4", "", "  "]
        options.ignore = [""]
        let request = DownloadRequest(DownloadJob(url: "https://bunkr.cr/a/test", options: options))
        XCTAssertEqual(request.include, [".mp4"])
        XCTAssertEqual(request.ignore, [])
    }
}

final class EngineLifecycleTests: XCTestCase {
    @MainActor private func fixture(_ script: String) throws -> (DownloadStore, URL) {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let engine = folder.appendingPathComponent("fixture-engine")
        try ("#!/bin/sh\nread request\n" + script).write(to: engine, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: engine.path)
        return (DownloadStore(support: folder, engine: engine), folder)
    }
    @MainActor private func waitForExit(_ store: DownloadStore) async {
        for _ in 0..<100 {
            if !store.isRunning { return }
            try? await Task.sleep(nanoseconds: 50_000_000)
        }
        XCTFail("Engine did not exit")
        store.stop()
    }
    @MainActor func testSuccessfulEngineDrainsLastResultBeforeExit() async throws {
        let (store, folder) = try fixture("printf '%s\\n' '{\"event\":\"summary\",\"completed\":2}' '{\"event\":\"result\",\"success\":true}'\n")
        defer { try? FileManager.default.removeItem(at: folder) }
        _ = store.add("bunkr.cr/a/test")
        store.start()
        await waitForExit(store)
        XCTAssertEqual(store.jobs[0].status, .completed)
        XCTAssertEqual(store.jobs[0].completed, 2)
    }
    @MainActor func testCleanExitWithoutResultIsFailure() async throws {
        let (store, folder) = try fixture("exit 0\n")
        defer { try? FileManager.default.removeItem(at: folder) }
        _ = store.add("bunkr.cr/a/test")
        store.start()
        await waitForExit(store)
        XCTAssertEqual(store.jobs[0].status, .failed)
    }
    @MainActor func testCancellationDoesNotStartNextJob() async throws {
        let (store, folder) = try fixture("exec /bin/sleep 30\n")
        defer { try? FileManager.default.removeItem(at: folder) }
        _ = store.add("bunkr.cr/a/one\nbunkr.cr/a/two")
        store.start()
        store.stop()
        await waitForExit(store)
        XCTAssertEqual(store.jobs[0].status, .cancelled)
        XCTAssertEqual(store.jobs[1].status, .queued)
    }
}
