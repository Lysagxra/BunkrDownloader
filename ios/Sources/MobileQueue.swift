import Foundation
import Observation

struct MobileJob: Identifiable, Codable {
    enum Status: String, Codable { case queued, running, stopped, failed, finished }
    var id = UUID()
    let link: URL
    var status: Status = .queued
    var items: [URL]?
    var title: String?
    var wifiOnly: Bool?
    var failures: [String: String]?
    var received: Int64?
    var expected: Int64?
    var total = 0
    var files: [String: String] = [:] // Canonical item URL to filename within the job's folder.
    var detail = "Ready to download"
    var folderName: String { "\(link.lastPathComponent.prefix(45))-\(id.uuidString)" }
}

@MainActor @Observable
final class MobileQueue {
    private(set) var jobs: [MobileJob] = []
    private(set) var active = false
    private(set) var stopping = false
    var wifiOnly = false
    var error: String?
    private let state: URL
    let documents: URL
    private let service: TransferService
    private var writable = true
    @ObservationIgnored private var worker: Task<Void, Never>?

    init(state: URL = URL.applicationSupportDirectory.appending(path: "queue.json"),
         documents: URL = .documentsDirectory, service: TransferService = TransferService()) {
        self.state = state
        self.documents = documents
        self.service = service
        var resume = false
        do {
            try FileManager.default.createDirectory(at: state.deletingLastPathComponent(), withIntermediateDirectories: true)
            if FileManager.default.fileExists(atPath: state.path) {
                jobs = try JSONDecoder().decode([MobileJob].self, from: Data(contentsOf: state))
                for i in jobs.indices where jobs[i].status == .running {
                    #if os(iOS)
                    jobs[i].status = .queued
                    resume = true
                    #else
                    jobs[i].status = .stopped
                    #endif
                    jobs[i].detail = "Interrupted. Retry to continue."
                }
            }
        } catch {
            writable = false
            self.error = "Could not open the queue. Its saved data has been preserved. \(error.localizedDescription)"
        }
        #if os(iOS)
        BackgroundTransfers.shared.reconnect()
        if resume { start() }
        #endif
    }

    @discardableResult private func save() -> Bool {
        guard writable else { return false }
        do {
            try JSONEncoder().encode(jobs).write(to: state, options: .atomic)
            return true
        } catch {
            self.error = "Could not save the queue. \(error.localizedDescription)"
            return false
        }
    }

    func add(_ text: String) -> Bool {
        guard writable else { error = "The saved queue could not be opened."; return false }
        let lines = text.split(whereSeparator: \.isNewline).map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        let urls = lines.compactMap(LinkParser.normalize).compactMap(URL.init(string:))
        guard !urls.isEmpty, urls.count == lines.count else {
            error = "Enter one Bunkr album or file link per line, using /a/, /f/, /i/, or /v/."
            return false
        }
        let before = jobs.count
        for link in urls where !jobs.contains(where: { $0.link == link && [.queued, .running].contains($0.status) }) {
            var job = MobileJob(link: link)
            job.wifiOnly = wifiOnly
            jobs.append(job)
        }
        guard jobs.count > before else { error = "These links are already queued."; return false }
        guard save() else { jobs.removeSubrange(before...); return false }
        return true
    }

    func start() {
        guard writable, !active, jobs.contains(where: { $0.status == .queued }) else { return }
        active = true
        worker = Task {
            defer { active = false; stopping = false; worker = nil }
            while !Task.isCancelled, let i = jobs.firstIndex(where: { $0.status == .queued }) {
                // Entries can be appended while running, but removal is disabled until the queue stops.
                jobs[i].status = .running
                jobs[i].detail = "Finding files…"
                guard save() else { jobs[i].status = .stopped; break }
                do {
                    if jobs[i].title == nil { jobs[i].title = try? await service.title(for: jobs[i].link) }
                    let items: [URL]
                    if let saved = jobs[i].items { items = saved }
                    else {
                        items = try await service.items(for: jobs[i].link)
                        jobs[i].items = items
                        guard save() else { jobs[i].status = .stopped; return }
                    }
                    let folder = documents.appending(path: jobs[i].folderName, directoryHint: .isDirectory)
                    jobs[i].total = items.count
                    jobs[i].failures = [:]
                    for (offset, item) in items.enumerated() {
                        try Task.checkCancellation()
                        let key = item.absoluteString
                        if let name = jobs[i].files[key], FileManager.default.fileExists(atPath: folder.appending(path: name).path) { continue }
                        jobs[i].received = 0
                        jobs[i].expected = nil
                        let jobID = jobs[i].id
                        jobs[i].detail = "File \(offset + 1) of \(items.count) · \(item.lastPathComponent)"
                        do {
                            let name = try await service.download(item, into: folder, wifiOnly: jobs[i].wifiOnly ?? false) { received, expected in
                                Task { @MainActor in
                                    guard let index = self.jobs.firstIndex(where: { $0.id == jobID && $0.status == .running }) else { return }
                                    self.jobs[index].received = received
                                    self.jobs[index].expected = expected > 0 ? expected : nil
                                }
                            }
                            jobs[i].files[key] = name
                        } catch {
                            try Task.checkCancellation()
                            jobs[i].failures?[key] = error.localizedDescription
                        }
                        guard save() else { jobs[i].status = .stopped; return }
                    }
                    let failures = jobs[i].failures?.count ?? 0
                    jobs[i].status = failures == 0 ? .finished : .failed
                    jobs[i].detail = "\(jobs[i].files.count) saved · \(failures) failed"
                } catch {
                    jobs[i].status = Task.isCancelled ? .stopped : .failed
                    jobs[i].detail = Task.isCancelled ? "Stopped. Retry to continue." : error.localizedDescription
                }
                guard save() else { break }
            }
        }
    }

    func stop() { stopping = true; worker?.cancel() }

    func retry(_ id: UUID) {
        guard writable, let i = jobs.firstIndex(where: { $0.id == id }),
              [.failed, .stopped].contains(jobs[i].status) else { return }
        let previous = jobs[i]
        jobs[i].status = .queued
        jobs[i].detail = "Ready to retry"
        guard save() else { jobs[i] = previous; return }
        start()
    }

    func remove(_ id: UUID) {
        guard writable, !active else { return }
        guard let index = jobs.firstIndex(where: { $0.id == id }) else { return }
        let removed = jobs.remove(at: index)
        if !save() { jobs.insert(removed, at: index) }
    }
}
