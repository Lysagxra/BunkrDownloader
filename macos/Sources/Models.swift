import Foundation

struct DownloadOptions: Codable, Equatable {
    var destination = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Downloads").path
    var connections = 4
    var retries = 5
    var rateLimit = 0
    var cleanNames = true
    var albumFolders = true
    var include: [String] = []
    var ignore: [String] = []
}

enum DownloadStatus: String, Codable {
    case queued, running, completed, failed, cancelled
    var label: String { rawValue.capitalized }
}

struct DownloadJob: Codable, Identifiable {
    var id = UUID()
    var url: String
    var options: DownloadOptions
    var status: DownloadStatus = .queued
    var received: Int64?
    var expected: Int64?
    var progress = 0.0
    var completed = 0
    var skipped = 0
    var failed = 0
    var total = 0
    var message = "Ready to download"
    var logs: [String] = []
    var created = Date()
    var title: String { URL(string: url)?.lastPathComponent ?? url }
    var isAlbum: Bool { URL(string: url)?.path.hasPrefix("/a/") == true }
}

struct EngineEvent: Decodable {
    var event: String
    var message: String?
    var received: Int64?
    var expected: Int64?
    var rows: [PreviewRow]?
    var progress: Double?
    var total: Int?
    var completed: Int?
    var skipped: Int?
    var failed: Int?
    var success: Bool?
}

struct DownloadRequest: Encodable {
    var preview: Bool?
    var url: String
    var destination: String
    var connections: Int
    var retries: Int
    var rateLimit: Int
    var cleanNames: Bool
    var albumFolders: Bool
    var include: [String]
    var ignore: [String]
    init(_ job: DownloadJob) {
        url = job.url
        let o = job.options
        destination = o.destination; connections = o.connections; retries = o.retries
        rateLimit = o.rateLimit; cleanNames = o.cleanNames; albumFolders = o.albumFolders
        include = o.include.map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        ignore = o.ignore.map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    }
}

struct SavedState: Codable {
    var options: DownloadOptions
    var jobs: [DownloadJob]
}


struct PreviewRow: Decodable, Identifiable {
    var id: String { filename + status }
    var filename: String
    var size: Int64?
    var status: String
}
