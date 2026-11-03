#if os(iOS)
import Foundation
import UIKit

/// The task description is the durable item mapping owned by the system session.
/// Completion receipts are written before acknowledging background events.
@MainActor
final class BackgroundTransfers: NSObject, @preconcurrency URLSessionDownloadDelegate {
    static let shared = BackgroundTransfers()
    static let identifier = "com.bunkrdownloader.media"
    struct Record: Codable {
        let key: String
        let destination: URL
    }
    struct Receipt: Codable {
        let file: URL?
        let error: String?
    }
    private var waiters: [String: CheckedContinuation<URL, Error>] = [:]
    var progress: ((String, Int64, Int64) -> Void)?
    var finishedEvents: (() -> Void)?
    private lazy var session: URLSession = {
        let configuration = URLSessionConfiguration.background(withIdentifier: Self.identifier)
        configuration.sessionSendsLaunchEvents = true
        configuration.isDiscretionary = false
        return URLSession(configuration: configuration, delegate: self, delegateQueue: .main)
    }()
    private let receipts = URL.applicationSupportDirectory.appending(path: "Transfers", directoryHint: .isDirectory)

    func reconnect() { _ = session }

    func recover(key: String) async throws -> URL? {
        if let bytes = try? Data(contentsOf: receiptURL(key)),
           let receipt = try? JSONDecoder().decode(Receipt.self, from: bytes),
           let file = receipt.file, FileManager.default.fileExists(atPath: file.path) {
            return file
        }
        let tasks = await session.allTasks
        guard let task = tasks.first(where: { decode($0)?.key == key }),
              let record = decode(task), let request = task.originalRequest else { return nil }
        return try await download(request, key: key, destination: record.destination)
    }


    private func receiptURL(_ key: String) -> URL {
        receipts.appending(path: Data(key.utf8).base64EncodedString().replacingOccurrences(of: "/", with: "_"))
    }

    func download(_ request: URLRequest, key: String, destination: URL) async throws -> URL {
        if let bytes = try? Data(contentsOf: receiptURL(key)),
           let receipt = try? JSONDecoder().decode(Receipt.self, from: bytes) {
            if let file = receipt.file, FileManager.default.fileExists(atPath: file.path) { return file }
            try FileManager.default.removeItem(at: receiptURL(key))
        }
        let tasks = await session.allTasks
        try Task.checkCancellation()
        if let bytes = try? Data(contentsOf: receiptURL(key)),
           let receipt = try? JSONDecoder().decode(Receipt.self, from: bytes) {
            if let file = receipt.file, FileManager.default.fileExists(atPath: file.path) { return file }
            if let error = receipt.error {
                try? FileManager.default.removeItem(at: receiptURL(key))
                throw TransferError(error)
            }
        }
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                if Task.isCancelled { continuation.resume(throwing: CancellationError()); return }
                waiters[key] = continuation
                if tasks.contains(where: { decode($0)?.key == key }) { return }
                var target = destination
                var suffix = 2
                while FileManager.default.fileExists(atPath: target.path) {
                    target = destination.deletingPathExtension()
                        .appendingPathExtension(String(suffix) + (destination.pathExtension.isEmpty ? "" : "." + destination.pathExtension))
                    suffix += 1
                }
                let task = session.downloadTask(with: request)
                task.taskDescription = String(data: try! JSONEncoder().encode(Record(key: key, destination: target)), encoding: .utf8)
                task.resume()
            }
        } onCancel: {
            DispatchQueue.main.async {
                self.session.getAllTasks { tasks in
                    tasks.filter { self.decode($0)?.key == key }.forEach { $0.cancel() }
                }
            }
        }
    }

    nonisolated private func decode(_ task: URLSessionTask) -> Record? {
        guard let bytes = task.taskDescription?.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode(Record.self, from: bytes)
    }

    private func complete(_ record: Record, file: URL?, error: Error?) {
        do {
            try FileManager.default.createDirectory(at: receipts, withIntermediateDirectories: true)
            try JSONEncoder().encode(Receipt(file: file, error: error?.localizedDescription))
                .write(to: receiptURL(record.key), options: .atomic)
            if let error { waiters.removeValue(forKey: record.key)?.resume(throwing: error) }
            else if let file { waiters.removeValue(forKey: record.key)?.resume(returning: file) }
        } catch {
            waiters.removeValue(forKey: record.key)?.resume(throwing: error)
        }
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL) {
        guard let record = decode(downloadTask) else { return }
        do {
            guard record.destination.isFileURL,
                  record.destination.standardizedFileURL.path.hasPrefix(URL.documentsDirectory.standardizedFileURL.path + "/"),
                  !((try? record.destination.deletingLastPathComponent().resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) ?? false)
            else { throw TransferError("The destination folder is no longer available.") }
            guard let response = downloadTask.response as? HTTPURLResponse,
                  response.statusCode == 200, response.mimeType != "text/html", response.mimeType != "application/json" else {
                throw TransferError("The media request expired or returned an error page. Retry to refresh its link.")
            }
            let size = try location.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
            guard size > 0, response.expectedContentLength < 0 || Int64(size) == response.expectedContentLength else {
                throw TransferError("The media transfer was incomplete.")
            }
            try FileManager.default.createDirectory(at: record.destination.deletingLastPathComponent(), withIntermediateDirectories: true)
            // Never adopt a file created by another app while this task was running.
            guard !FileManager.default.fileExists(atPath: record.destination.path) else {
                throw TransferError("The destination file already exists. Retry to save a separate copy.")
            }
            try FileManager.default.moveItem(at: location, to: record.destination)
            complete(record, file: record.destination, error: nil)
        } catch { complete(record, file: nil, error: error) }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error, let record = decode(task) { complete(record, file: nil, error: error) }
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didWriteData bytesWritten: Int64,
                    totalBytesWritten: Int64, totalBytesExpectedToWrite: Int64) {
        if let record = decode(downloadTask) { progress?(record.key, totalBytesWritten, totalBytesExpectedToWrite) }
    }

    func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
        let handler = finishedEvents
        finishedEvents = nil
        handler?()
    }
}

final class MobileAppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication, handleEventsForBackgroundURLSession identifier: String,
                     completionHandler: @escaping () -> Void) {
        BackgroundTransfers.shared.finishedEvents = completionHandler
        BackgroundTransfers.shared.reconnect()
    }
}
#endif
