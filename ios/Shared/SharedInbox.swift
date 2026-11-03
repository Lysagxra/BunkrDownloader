import Foundation

enum SharedInbox {
    static let group = "group.com.bunkrdownloader.shared"
    static func directory() throws -> URL {
        guard let root = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: group) else {
            throw NSError(domain: "Bunkr", code: 1, userInfo: [NSLocalizedDescriptionKey: "Shared storage is unavailable. Check the App Group signing configuration."])
        }
        let inbox = root.appending(path: "Inbox", directoryHint: .isDirectory)
        try FileManager.default.createDirectory(at: inbox, withIntermediateDirectories: true)
        return inbox
    }
    static func deposit(_ links: [String]) throws {
        try JSONEncoder().encode(links).write(to: directory().appending(path: UUID().uuidString + ".json"), options: .atomic)
    }
}
