import SwiftUI
import QuickLook

@main
struct BunkrMobile: App {
    @UIApplicationDelegateAdaptor(MobileAppDelegate.self) private var delegate
    @State private var queue = MobileQueue()

    var body: some Scene {
        WindowGroup { DownloadScreen(queue: queue).tint(.teal) }
    }
}

struct DownloadScreen: View {
    @Bindable var queue: MobileQueue
    @State private var adding = false
    @State private var input = ""
    @State private var preview: URL?
    @Environment(\.scenePhase) private var phase

    var body: some View {
        NavigationStack {
            List {
                if queue.jobs.isEmpty {
                    ContentUnavailableView("Your queue is empty", systemImage: "tray.and.arrow.down",
                                           description: Text("Add a Bunkr album or file link to download it to Files."))
                        .listRowBackground(Color.clear)
                } else {
                    Section {
                        ForEach(queue.jobs) { job in
                            NavigationLink {
                                jobDetails(id: job.id)
                            } label: {
                                VStack(alignment: .leading, spacing: 6) {
                                    Label(job.title ?? job.link.lastPathComponent, systemImage: job.link.path.hasPrefix("/a/") ? "rectangle.stack" : "doc")
                                        .font(.headline)
                                    Text(job.status.rawValue.capitalized).font(.subheadline.weight(.medium))
                                    Text(job.detail).font(.caption).foregroundStyle(.secondary)
                                    Text("\(job.files.count) of \(job.total) files saved").font(.caption)
                                    if job.status == .running {
                                        if let expected = job.expected, expected > 0 {
                                            ProgressView(value: Double(job.received ?? 0), total: Double(expected))
                                                .accessibilityLabel("Current file bytes received")
                                        } else { ProgressView().accessibilityLabel("Waiting for file size") }
                                        Text("\(ByteCountFormatter.string(fromByteCount: job.received ?? 0, countStyle: .file)) received for current file").font(.caption)
                                    }
                                }.padding(.vertical, 4)
                            }
                        }.onDelete { offsets in
                            let ids = offsets.map { queue.jobs[$0].id }
                            ids.forEach(queue.remove)
                        }.deleteDisabled(queue.active)
                    } footer: {
                        Text("Media transfers continue in the background. Find saved files in Files → On My iPhone or iPad → Bunkr.")
                    }
                }
            }
            .quickLookPreview($preview)
            .task { importSharedLinks() }
            .onChange(of: phase) { _, phase in if phase == .active { importSharedLinks() } }
            .navigationTitle("Downloads")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button("Add links", systemImage: "plus") { adding = true }
                }
                ToolbarItem(placement: .bottomBar) {
                    if queue.active {
                        Button(queue.stopping ? "Stopping…" : "Stop queue", systemImage: "stop.fill") { queue.stop() }
                            .disabled(queue.stopping)
                    } else {
                        Button("Start queue", systemImage: "play.fill") { queue.start() }
                            .disabled(!queue.jobs.contains { $0.status == .queued })
                    }
                }
            }
            .sheet(isPresented: $adding) {
                NavigationStack {
                    Form {
                        Toggle("Wi-Fi only for new downloads", isOn: $queue.wifiOnly)
                        Section("Album or file links") {
                            TextField("One link per line", text: $input, axis: .vertical)
                                .lineLimit(4...10).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                        }
                        Button("Add to queue") {
                            if queue.add(input) { input = ""; adding = false }
                        }.disabled(input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        if let error = queue.error { Text(error).foregroundStyle(.red) }
                    }.navigationTitle("Add downloads")
                    .toolbar { Button("Done") { adding = false } }
                }.presentationDetents([.medium, .large])
            }
            .onChange(of: adding) { _, _ in queue.error = nil }
            .alert("Download queue", isPresented: Binding(get: { !adding && queue.error != nil }, set: { if !$0 { queue.error = nil } })) {
                Button("OK") { queue.error = nil }
            } message: { Text(queue.error ?? "") }
        }
    }

    private func importSharedLinks() {
        do {
            let directory = try SharedInbox.directory()
            for file in try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil) where file.pathExtension == "json" {
                let links = try JSONDecoder().decode([String].self, from: Data(contentsOf: file))
                let pending = links.filter { link in !queue.jobs.contains { $0.link.absoluteString == link } }
                if pending.isEmpty || queue.add(pending.joined(separator: "\n")) {
                    try FileManager.default.removeItem(at: file)
                }
            }
        } catch { queue.error = error.localizedDescription }
    }

    @ViewBuilder private func jobDetails(id: UUID) -> some View {
        if let job = queue.jobs.first(where: { $0.id == id }) {
            List {
                Section("Source") { Text(job.link.absoluteString).textSelection(.enabled) }
                Section(job.status.rawValue.capitalized) {
                    Text(job.detail)
                    if [.stopped, .failed].contains(job.status) { Button("Retry failed files") { queue.retry(id) } }
                }
                if let failures = job.failures, !failures.isEmpty {
                    Section("Failed files") {
                        ForEach(failures.keys.sorted(), id: \.self) { key in
                            VStack(alignment: .leading) {
                                Text(URL(string: key)?.lastPathComponent ?? key)
                                Text(failures[key] ?? "").foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                if !job.files.isEmpty {
                    Section("Saved files") {
                        ForEach(job.files.values.sorted(), id: \.self) { name in
                            let url = queue.documents.appending(path: job.folderName).appending(path: name)
                            if FileManager.default.fileExists(atPath: url.path) {
                                Button(name) { preview = url }
                                ShareLink(item: url) { Label(name, systemImage: "square.and.arrow.up") }
                            } else { Text("\(name) · Moved or removed").foregroundStyle(.secondary) }
                        }
                    }
                }
            }.navigationTitle(job.title ?? job.link.lastPathComponent)
        }
    }
}
