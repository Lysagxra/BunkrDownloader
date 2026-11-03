import AppKit
import Combine
import Foundation

@MainActor
final class DownloadStore: ObservableObject {
    @Published var jobs: [DownloadJob] = []
    @Published var options = DownloadOptions()
    @Published var selectedID: UUID?
    @Published var isRunning = false
    @Published var stopping = false
    @Published var error: String?
    @Published var engineReady = false
    @Published var previewRows: [PreviewRow] = []
    @Published var previewing = false
    private var previewWorker: Process?
    private var process: Process?
    private var runQueue = false
    private var finalSuccess: Bool?
    private var canSave = true
    private let support: URL
    private let engine: URL
    private var stateFile: URL { support.appendingPathComponent("queue.json") }

    init(support: URL? = nil, engine: URL? = nil) {
        self.support = support ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Bunkr", isDirectory: true)
        self.engine = engine ?? Bundle.main.bundleURL.appendingPathComponent("Contents/Resources/BunkrEngine/BunkrEngine")
        engineReady = FileManager.default.isExecutableFile(atPath: self.engine.path)
        do {
            try FileManager.default.createDirectory(at: self.support, withIntermediateDirectories: true)
            if FileManager.default.fileExists(atPath: stateFile.path) {
                let saved = try JSONDecoder().decode(SavedState.self, from: Data(contentsOf: stateFile))
                options = saved.options
                jobs = saved.jobs.map { job in
                    var job = job
                    if job.status == .running {
                        job.status = .cancelled
                        job.message = "Interrupted last session. Retry to continue."
                    }
                    return job
                }
            }
        } catch {
            canSave = false
            self.error = "Could not read saved queue. It has been preserved: \(error.localizedDescription)"
        }
    }

    func save() {
        guard canSave else { return }
        do {
            let data = try JSONEncoder().encode(SavedState(options: options, jobs: jobs))
            try data.write(to: stateFile, options: .atomic)
        } catch { self.error = "Could not save queue: \(error.localizedDescription)" }
    }

    @discardableResult func add(_ text: String) -> Bool {
        let lines = text.split(whereSeparator: \.isNewline).map(String.init).filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
        guard !lines.isEmpty else { return false }
        let urls = lines.compactMap(LinkParser.normalize)
        guard urls.count == lines.count else {
            error = "Use one Bunkr album or file link per line. Links must use HTTPS and contain /a/, /f/, /i/, or /v/."
            return false
        }
        var firstID: UUID?
        for url in urls where !jobs.contains(where: { $0.url == url && ($0.status == .queued || $0.status == .running) }) {
            let job = DownloadJob(url: url, options: options)
            jobs.append(job)
            firstID = firstID ?? job.id
        }
        selectedID = firstID ?? selectedID
        save()
        return true
    }

    func start() {
        guard !isRunning, engineReady else { return }
        runQueue = true
        startNext()
    }

    private func startNext() {
        guard runQueue, let index = jobs.firstIndex(where: { $0.status == .queued }) else {
            runQueue = false
            return
        }
        let job = jobs[index]
        let worker = Process()
        let output = Pipe(), input = Pipe()
        worker.executableURL = engine
        worker.currentDirectoryURL = support
        worker.standardInput = input
        worker.standardOutput = output
        let diagnostics = Pipe()
        worker.standardError = diagnostics
        let diagnostic = support.appendingPathComponent("engine.log")
        do {
            let request = try JSONEncoder().encode(DownloadRequest(job)) + Data([10])
            try worker.run()
            DispatchQueue.global(qos: .utility).async {
                var pending = Data()
                let handle = diagnostics.fileHandleForReading
                while true {
                    let chunk = handle.availableData
                    if chunk.isEmpty { break }
                    pending.append(chunk)
                    while let end = pending.firstIndex(of: 10) {
                        let line = String(decoding: pending.prefix(upTo: end), as: UTF8.self)
                        DiagnosticLog.append(line, to: diagnostic)
                        pending.removeSubrange(...end)
                    }
                    if pending.count > DiagnosticLog.limit { pending.removeAll() }
                }
                if !pending.isEmpty { DiagnosticLog.append(String(decoding: pending, as: UTF8.self), to: diagnostic) }
            }
            process = worker
            finalSuccess = nil
            isRunning = true
            stopping = false
            jobs[index].status = .running
            jobs[index].message = "Connecting…"
            selectedID = job.id
            save()
            // One reader preserves event/exit ordering and drains stdout before completion.
            DispatchQueue.global(qos: .utility).async { [weak self] in
                var pending = Data()
                let handle = output.fileHandleForReading
                while true {
                    let chunk = handle.availableData
                    if chunk.isEmpty { break }
                    pending.append(chunk)
                    while let end = pending.firstIndex(of: 10) {
                        let line = pending.prefix(upTo: end)
                        pending.removeSubrange(...end)
                        if let event = try? JSONDecoder().decode(EngineEvent.self, from: line) {
                            DispatchQueue.main.async { self?.receive(event, id: job.id) }
                        }
                    }
                    if pending.count > 1_048_576 { pending.removeAll() }
                }
                worker.waitUntilExit()
                try? handle.close()
                let status = worker.terminationStatus
                DispatchQueue.main.async { self?.finished(id: job.id, exit: status) }
            }
            try input.fileHandleForWriting.write(contentsOf: request)
            try input.fileHandleForWriting.close()
        } catch {
            if worker.isRunning { worker.terminate() }
            try? input.fileHandleForWriting.close()
            jobs[index].status = .failed
            jobs[index].message = error.localizedDescription
            self.error = "Could not start the download: \(error.localizedDescription)"
            runQueue = false
            if !isRunning { process = nil }
            save()
        }
    }

    private func receive(_ event: EngineEvent, id: UUID) {
        guard let i = jobs.firstIndex(where: { $0.id == id }) else { return }
        if event.event == "bytes" {
            jobs[i].received = event.received
            jobs[i].expected = event.expected
        }
        if let value = event.progress, value.isFinite { jobs[i].progress = min(max(value, 0), 1) }
        if let value = event.total { jobs[i].total = value }
        if let value = event.completed { jobs[i].completed = value }
        if let value = event.skipped { jobs[i].skipped = value }
        if let value = event.failed { jobs[i].failed = value }
        if let message = event.message {
            jobs[i].message = DiagnosticLog.redact(message)
            jobs[i].logs.append(DiagnosticLog.redact(message))
            if jobs[i].logs.count > 300 { jobs[i].logs.removeFirst(jobs[i].logs.count - 300) }
        }
        if event.event == "result" { finalSuccess = event.success }
    }

    private func finished(id: UUID, exit: Int32) {
        if let i = jobs.firstIndex(where: { $0.id == id }) {
            jobs[i].status = stopping ? .cancelled : (exit == 0 && finalSuccess == true ? .completed : .failed)
            if stopping { jobs[i].message = "Stopped. Retry to reuse completed files and saved chunks." }
            else if jobs[i].status == .completed {
                jobs[i].progress = 1
                jobs[i].message = "\(jobs[i].completed) downloaded · \(jobs[i].skipped) skipped"
            } else if jobs[i].logs.isEmpty { jobs[i].message = "Engine exited with code \(exit). Open the engine log for details." }
        }
        process = nil; isRunning = false; stopping = false
        save()
        startNext()
    }

    func stop() {
        runQueue = false
        guard let worker = process, worker.isRunning else { return }
        stopping = true
        worker.terminate()
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self, weak worker] in
            guard let self, let worker, self.process === worker, worker.isRunning else { return }
            kill(worker.processIdentifier, SIGKILL)
        }
    }

    func retry(_ id: UUID) {
        guard let i = jobs.firstIndex(where: { $0.id == id }), jobs[i].status != .running else { return }
        jobs[i].received = nil; jobs[i].expected = nil
        jobs[i].status = .queued; jobs[i].progress = 0
        jobs[i].completed = 0; jobs[i].skipped = 0; jobs[i].failed = 0; jobs[i].total = 0
        jobs[i].logs = []; jobs[i].message = "Ready to retry"
        save()
    }
    func remove(_ id: UUID) { jobs.removeAll { $0.id == id && $0.status != .running }; save() }
    func clearFinished() { jobs.removeAll { $0.status == .completed }; save() }
    func reveal(_ path: String) { NSWorkspace.shared.open(URL(fileURLWithPath: path)) }
    func openLog() { NSWorkspace.shared.open(support.appendingPathComponent("engine.log")) }
    func clearHistory() {
        jobs.removeAll { $0.status != .running }
        selectedID = jobs.first?.id
        save()
    }

    func exportDiagnostics() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "Bunkr-diagnostics.txt"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            let log = support.appendingPathComponent("engine.log")
            let text = (try? String(contentsOf: log, encoding: .utf8)) ?? ""
            try DiagnosticLog.redact(text + "\n" + jobs.flatMap(\.logs).joined(separator: "\n"))
                .write(to: url, atomically: true, encoding: .utf8)
        } catch { self.error = error.localizedDescription }
    }

    func cancelPreview() {
        previewWorker?.terminate()
        previewWorker = nil
        previewing = false
    }

    func preview(_ text: String) {
        cancelPreview()
        previewRows = []
        guard let link = text.split(whereSeparator: \.isNewline).first.flatMap({ LinkParser.normalize(String($0)) }) else { return }
        let worker = Process()
        let input = Pipe(), output = Pipe()
        worker.executableURL = engine
        worker.currentDirectoryURL = support
        worker.standardInput = input
        worker.standardOutput = output
        worker.standardError = FileHandle.nullDevice
        do {
            var request = DownloadRequest(DownloadJob(url: link, options: options))
            request.preview = true
            try worker.run()
            previewWorker = worker
            previewing = true
            DispatchQueue.global(qos: .utility).async { [weak self] in
                let bytes = output.fileHandleForReading.readDataToEndOfFile()
                worker.waitUntilExit()
                let events = bytes.split(separator: 10).compactMap { try? JSONDecoder().decode(EngineEvent.self, from: Data($0)) }
                DispatchQueue.main.async {
                    guard self?.previewWorker === worker else { return }
                    self?.previewRows = events.compactMap(\.rows).flatMap { $0 }
                    self?.previewing = false
                    if worker.terminationStatus != 0 { self?.error = events.compactMap(\.message).last ?? "Preview failed." }
                }
            }
            try input.fileHandleForWriting.write(contentsOf: JSONEncoder().encode(request) + Data([10]))
            try input.fileHandleForWriting.close()
        } catch { self.error = error.localizedDescription; cancelPreview() }
    }

    func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true; panel.canChooseFiles = false
        panel.canCreateDirectories = true; panel.prompt = "Choose Download Folder"
        panel.directoryURL = URL(fileURLWithPath: options.destination)
        if panel.runModal() == .OK, let url = panel.url { options.destination = url.path; save() }
    }
}


enum DiagnosticLog {
    static let limit = 1_048_576
    static func redact(_ text: String) -> String {
        text.replacingOccurrences(of: #"(?i)(token|ex|signature|authorization|api_key|auth)=([^&\s"<>]+)"#,
                                  with: "$1=REDACTED", options: .regularExpression)
    }
    static func append(_ text: String, to url: URL) {
        let bytes = Data((redact(text) + "\n").utf8)
        guard bytes.count <= limit else { return }
        do {
            let size = (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber)?.intValue ?? 0
            if size + bytes.count > limit {
                let old = url.appendingPathExtension("1")
                try? FileManager.default.removeItem(at: old)
                try FileManager.default.moveItem(at: url, to: old)
            }
            if !FileManager.default.fileExists(atPath: url.path) { FileManager.default.createFile(atPath: url.path, contents: nil) }
            let handle = try FileHandle(forWritingTo: url)
            defer { try? handle.close() }
            try handle.seekToEnd()
            try handle.write(contentsOf: bytes)
        } catch { /* Diagnostics must not interrupt media downloads. */ }
    }
}
