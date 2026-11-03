import SwiftUI
import AppKit

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    weak var store: DownloadStore?
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let store, store.isRunning else { return .terminateNow }
        let alert = NSAlert()
        alert.messageText = "Stop downloads and quit?"
        alert.informativeText = "Queued links are saved. Completed files and reusable chunks stay in your download folder."
        alert.addButton(withTitle: "Stop and Quit")
        alert.addButton(withTitle: "Keep Downloading")
        guard alert.runModal() == .alertFirstButtonReturn else { return .terminateCancel }
        store.stop()
        // Keep the app alive until the child exits; never orphan an active engine.
        Task { @MainActor in
            while store.isRunning { try? await Task.sleep(nanoseconds: 100_000_000) }
            sender.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }
}

@main
struct BunkrApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var store = DownloadStore()
    var body: some Scene {
        WindowGroup("Bunkr", id: "main") {
            ContentView(store: store)
                .frame(minWidth: 900, minHeight: 640)
                .tint(.teal)
                .onAppear { delegate.store = store }
        }
        .defaultSize(width: 1100, height: 760)
        .commands {
            CommandGroup(replacing: .newItem) { }
            CommandMenu("Downloads") {
                Button("Start Queue") { store.start() }.keyboardShortcut("r")
                    .disabled(store.isRunning || !store.jobs.contains { $0.status == .queued })
                Button("Stop Downloads") { store.stop() }.keyboardShortcut(".")
                    .disabled(!store.isRunning)
                Divider()
                Button("Open Download Folder") { store.reveal(store.options.destination) }.keyboardShortcut("o", modifiers: [.command, .shift])
                Button("Open Engine Log") { store.openLog() }
            }
        }
        Settings { OptionsView(store: store).padding(24).frame(width: 500).tint(.teal) }
    }
}
