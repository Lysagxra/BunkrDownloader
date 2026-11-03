import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct ContentView: View {
    @ObservedObject var store: DownloadStore
    @State private var input = ""
    @State private var filter = "All Downloads"
    @State private var search = ""
    @State private var showingPreview = false
    @State private var showOptions = false
    @State private var showActivity = true
    @FocusState private var inputFocused: Bool
    private let sections = ["All Downloads", "Queued", "Completed", "Needs Attention"]
    private var filtered: [DownloadJob] {
        store.jobs.filter { search.isEmpty || $0.url.localizedCaseInsensitiveContains(search) || $0.message.localizedCaseInsensitiveContains(search) }.filter { job in
            switch filter {
            case "Queued": return job.status == .queued || job.status == .running
            case "Completed": return job.status == .completed
            case "Needs Attention": return job.status == .failed || job.status == .cancelled
            default: return true
            }
        }
    }
    private var selected: DownloadJob? { store.jobs.first { $0.id == store.selectedID } }

    var body: some View {
        NavigationSplitView {
            VStack(alignment: .leading, spacing: 24) {
                HStack(spacing: 11) {
                    Image(systemName: "arrow.down.to.line.compact")
                        .font(.system(size: 23, weight: .bold)).foregroundStyle(.white)
                        .frame(width: 44, height: 44).background(.teal.gradient, in: RoundedRectangle(cornerRadius: 13))
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Bunkr").font(.title2.bold())
                        Text("DOWNLOAD MANAGER").font(.system(size: 8, weight: .semibold)).tracking(1.4).foregroundStyle(.secondary)
                    }
                }.padding(.horizontal, 18).padding(.top, 22)
                List(selection: $filter) {
                    ForEach(sections, id: \.self) { section in
                        Label("\(section) (\(count(section)))", systemImage: icon(section)).tag(section)
                    }
                }.listStyle(.sidebar)
                Spacer()
                VStack(alignment: .leading, spacing: 10) {
                    Label(store.engineReady ? "Engine ready" : "Engine missing", systemImage: store.engineReady ? "checkmark.circle.fill" : "exclamationmark.triangle")
                        .font(.caption.weight(.medium)).foregroundStyle(store.engineReady ? Color.teal : .orange)
                    Text("Albums and files, organized.\nPowered by Bunkr Downloader.")
                        .font(.caption).foregroundStyle(.secondary).lineSpacing(3)
                    Button { showOptions = true } label: { Label("Download Settings", systemImage: "slider.horizontal.3") }
                        .buttonStyle(.plain).font(.caption).padding(.top, 6)
                }.padding(20)
            }.navigationSplitViewColumnWidth(min: 210, ideal: 220, max: 260)
        } detail: {
            VStack(alignment: .leading, spacing: 0) {
                header
                composer.padding(.horizontal, 26).padding(.bottom, 20)
                HStack {
                    Text(filter).font(.headline)
                    Text("\(filtered.count)").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    Spacer()
                    if store.jobs.contains(where: { $0.status == .completed }) {
                        Button("Clear Finished") { store.clearFinished() }.buttonStyle(.plain).font(.caption).foregroundStyle(.secondary)
                    }
                    Button { showActivity.toggle() } label: { Image(systemName: "sidebar.bottom") }
                        .buttonStyle(.plain).help("Toggle activity details")
                }.padding(.horizontal, 26).padding(.bottom, 10)
                Divider()
                if filtered.isEmpty { emptyState }
                else {
                    List(selection: $store.selectedID) {
                        ForEach(filtered) { job in
                            JobRow(job: job)
                                .padding(.vertical, 7).tag(job.id)
                                .contextMenu {
                                    if job.status == .failed || job.status == .cancelled || job.status == .completed {
                                        Button("Queue Again") { store.retry(job.id) }
                                    }
                                    Button("Open Download Folder") { store.reveal(job.options.destination) }
                                    Button("Copy Link") {
                                        NSPasteboard.general.clearContents()
                                        NSPasteboard.general.setString(job.url, forType: .string)
                                    }
                                    if job.status != .running { Button("Remove from List") { store.remove(job.id) } }
                                }
                        }
                    }.listStyle(.inset).scrollContentBackground(.hidden)
                }

                footer
            }.background(Color(nsColor: .textBackgroundColor))
        }
        .searchable(text: $search, prompt: "Search downloads")
        .inspector(isPresented: $showActivity) {
            if let job = selected { activity(job).frame(maxHeight: .infinity) }
            else { Text("Select a download").foregroundStyle(.secondary) }
        }
        .inspectorColumnWidth(min: 240, ideal: 320, max: 600)
        .sheet(isPresented: $showingPreview, onDismiss: { store.cancelPreview() }) {
            VStack {
                HStack {
                    Text("Download preview").font(.title2)
                    Spacer()
                    Button("Refresh") { store.preview(input) }
                    Button("Done") { showingPreview = false }
                }
                Text("\(store.previewRows.filter { $0.status == "would_download" }.count) files to download")
                if store.previewing { ProgressView() }
                List(store.previewRows) { row in
                    HStack {
                        Text(row.filename)
                        Spacer()
                        Text(row.size.map { ByteCountFormatter.string(fromByteCount: $0, countStyle: .file) } ?? "Unknown size")
                        Text(row.status.replacingOccurrences(of: "_", with: " "))
                    }
                }
                OptionsView(store: store)
            }.padding().frame(minWidth: 650, minHeight: 650)
                .onChange(of: store.options) { _, _ in store.preview(input) }
        }
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button(store.isRunning ? "Stop" : "Start Queue", systemImage: store.isRunning ? "stop.fill" : "play.fill") {
                    if store.isRunning { store.stop() } else { store.start() }
                }
                Button("Export Diagnostics") { store.exportDiagnostics() }
                Button("Clear History") { store.clearHistory() }.disabled(store.isRunning)
                Button { store.reveal(store.options.destination) } label: { Label("Open Folder", systemImage: "folder") }
                Button { showOptions = true } label: { Label("Settings", systemImage: "slider.horizontal.3") }
            }
        }
        .sheet(isPresented: $showOptions) {
            VStack(alignment: .leading, spacing: 18) {
                HStack { Text("Download Settings").font(.title2.bold()); Spacer(); Button("Done") { store.save(); showOptions = false }.keyboardShortcut(.defaultAction) }
                OptionsView(store: store)
            }.padding(26).frame(width: 550)
        }
        .alert("Bunkr", isPresented: Binding(get: { store.error != nil }, set: { if !$0 { store.error = nil } })) {
            Button("OK") { store.error = nil }
        } message: { Text(store.error ?? "") }
    }

    private var header: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Your downloads, in order.").font(.system(size: 27, weight: .bold, design: .rounded))
                Text("Add a link. Choose a folder. Let Bunkr take it from here.").font(.subheadline).foregroundStyle(.secondary)
            }
            Spacer()
            if store.isRunning {
                Button { store.stop() } label: { Label(store.stopping ? "Stopping…" : "Stop", systemImage: "stop.fill") }
                    .disabled(store.stopping).controlSize(.large)
            } else {
                Button { store.start() } label: { Label("Start Queue", systemImage: "play.fill") }
                    .buttonStyle(.borderedProminent).controlSize(.large)
                    .disabled(!store.engineReady || !store.jobs.contains { $0.status == .queued })
            }
        }.padding(26)
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("ADD DOWNLOADS", systemImage: "link").font(.caption.weight(.semibold)).tracking(0.8).foregroundStyle(.secondary)
                Spacer()
                Button("Paste") {
                    if let text = NSPasteboard.general.string(forType: .string) { input = text }
                }.buttonStyle(.plain).font(.caption).foregroundStyle(.teal)
                Button("Import Links…") { importLinks() }.buttonStyle(.plain).font(.caption).foregroundStyle(.teal)
            }
            ZStack(alignment: .topLeading) {
                TextEditor(text: $input).font(.system(.body, design: .monospaced))
                    .scrollContentBackground(.hidden).frame(height: 64).focused($inputFocused)
                    .accessibilityLabel("Bunkr links, one per line")
                if input.isEmpty {
                    Text("Paste album or file links, one per line…").foregroundStyle(.tertiary).padding(.top, 2).padding(.leading, 5).allowsHitTesting(false)
                }
            }
            Divider()
            HStack(spacing: 8) {
                Image(systemName: "folder").foregroundStyle(.teal)
                Text(store.options.destination).font(.caption).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle).help(store.options.destination)
                Button("Change…") { store.chooseFolder() }.buttonStyle(.plain).font(.caption)
                Spacer()
                Button("Preview…") { showingPreview = true; store.preview(input) }.disabled(input.isEmpty || !store.engineReady)
                Button { if store.add(input) { input = ""; filter = "All Downloads" } } label: { Label("Add to Queue", systemImage: "plus") }
                    .disabled(input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .keyboardShortcut(.return, modifiers: .command)
            }
        }.padding(16).background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(.primary.opacity(0.08)))
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Spacer()
            Image(systemName: filter == "All Downloads" ? "tray.and.arrow.down" : icon(filter))
                .font(.system(size: 42, weight: .light)).foregroundStyle(.teal.opacity(0.7))
            Text(filter == "All Downloads" ? "Ready when you are" : "Nothing here yet").font(.title3.weight(.semibold))
            Text(filter == "All Downloads" ? "Paste your first Bunkr link above to build your queue.\nAlbums stay together. Existing files are skipped." : "Downloads will appear here as your queue progresses.")
                .font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center).lineSpacing(4)
            Spacer()
        }.frame(maxWidth: .infinity, maxHeight: .infinity).padding(20)
    }

    private func activity(_ job: DownloadJob) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Divider()
            HStack {
                Label("Activity", systemImage: "text.alignleft").font(.caption.weight(.semibold))
                Text(job.title).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                Spacer()
                if job.status == .failed || job.status == .cancelled {
                    Button("Retry") { store.retry(job.id); store.start() }.font(.caption)
                }
                Button("Show Folder") { store.reveal(job.options.destination) }.font(.caption)
            }.padding(.horizontal, 26)
            ScrollView {
                Text(job.logs.isEmpty ? job.message : job.logs.suffix(40).joined(separator: "\n"))
                    .font(.system(size: 11, design: .monospaced)).foregroundStyle(.secondary)
                    .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
            }.frame(minHeight: 160, maxHeight: .infinity).padding(.horizontal, 26).padding(.bottom, 8)
        }
    }
    private var footer: some View {
        HStack(spacing: 7) {
            Circle().fill(store.isRunning ? Color.teal : Color.secondary.opacity(0.5)).frame(width: 6, height: 6)
            Text(store.isRunning ? "\(store.stopping ? "Stopping downloads" : "Queue is running")" : "\(store.jobs.filter { $0.status == .queued }.count) queued")
            Spacer()
            Text("\(store.jobs.filter { $0.status == .completed }.count) finished")
        }.font(.caption).foregroundStyle(.secondary).padding(.horizontal, 26).padding(.vertical, 12).background(.bar)
    }
    private func icon(_ section: String) -> String {
        switch section { case "Queued": return "clock"; case "Completed": return "checkmark.circle"; case "Needs Attention": return "exclamationmark.circle"; default: return "tray.full" }
    }
    private func count(_ section: String) -> Int {
        switch section {
        case "Queued": return store.jobs.filter { $0.status == .queued || $0.status == .running }.count
        case "Completed": return store.jobs.filter { $0.status == .completed }.count
        case "Needs Attention": return store.jobs.filter { $0.status == .failed || $0.status == .cancelled }.count
        default: return store.jobs.count
        }
    }
    private func importLinks() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.plainText]; panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            do { input = try String(contentsOf: url, encoding: .utf8) }
            catch { store.error = "Could not read links: \(error.localizedDescription)" }
        }
    }
}

struct JobRow: View {
    let job: DownloadJob
    private var color: Color {
        switch job.status { case .completed: return .teal; case .failed: return .red; case .cancelled: return .orange; default: return .secondary }
    }
    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: job.isAlbum ? "rectangle.stack" : "doc")
                .font(.title3).foregroundStyle(.teal).frame(width: 42, height: 42)
                .background(.teal.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(job.title).font(.headline).lineLimit(1)
                    Text(job.isAlbum ? "ALBUM" : "FILE").font(.system(size: 8, weight: .semibold)).foregroundStyle(.secondary)
                    Spacer()
                    Text(job.status.label).font(.caption.weight(.medium)).foregroundStyle(color)
                }
                Text(job.url).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                if job.status == .running {
                    if let expected = job.expected, expected > 0 {
                        ProgressView(value: Double(job.received ?? 0), total: Double(expected)).tint(.teal)
                    } else { ProgressView().controlSize(.small) }
                    Text("\(ByteCountFormatter.string(fromByteCount: job.received ?? 0, countStyle: .file)) received").font(.caption)
                    HStack {
                        Text(job.total == 0 ? "Resolving files…" : "\(job.completed + job.skipped) of \(job.total) files finished")
                        Spacer()
                        Text(job.expected.map { ByteCountFormatter.string(fromByteCount: $0, countStyle: .file) + " expected" } ?? "Size unknown").monospacedDigit()
                    }.font(.caption2).foregroundStyle(.secondary)
                } else {
                    Text(job.message).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                }
            }
        }
    }
}

struct OptionsView: View {
    @ObservedObject var store: DownloadStore
    var body: some View {
        Form {
            Section("Save to") {
                HStack {
                    Text(store.options.destination).lineLimit(1).truncationMode(.middle)
                    Spacer()
                    Button("Choose…") { store.chooseFolder() }
                }
                Toggle("Keep each album in its own folder", isOn: $store.options.albumFolders)
                Toggle("Preserve original filenames", isOn: $store.options.cleanNames)
            }
            Section("Transfers") {
                Stepper("Connections per file: \(store.options.connections)", value: $store.options.connections, in: 1...16)
                Stepper("Download attempts: \(store.options.retries)", value: $store.options.retries, in: 1...10)
                Picker("Speed limit", selection: $store.options.rateLimit) {
                    Text("Unlimited").tag(0)
                    Text("512 KB/s").tag(512)
                    Text("1 MB/s").tag(1024)
                    Text("5 MB/s").tag(5120)
                    Text("10 MB/s").tag(10240)
                }
            }
            Section("Filename filters") {
                TextField("Include", text: filterBinding(\.include), prompt: Text("e.g. .mp4, holiday"))
                TextField("Exclude", text: filterBinding(\.ignore), prompt: Text("e.g. .zip, preview"))
                Text("Comma-separated, case-sensitive matches. Leave Include empty to allow all files.").font(.caption).foregroundStyle(.secondary)
            }
            Section {
                Text("Settings apply to newly added links. The queue runs one link at a time, with up to three album files downloading together. Byte totals cover resolved transfers. Unknown sizes remain indeterminate.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }.formStyle(.grouped).frame(height: 480)
            .onChange(of: store.options) { _, _ in store.save() }
    }
    private func filterBinding(_ key: WritableKeyPath<DownloadOptions, [String]>) -> Binding<String> {
        Binding(get: { store.options[keyPath: key].joined(separator: ",") }, set: {
            store.options[keyPath: key] = $0.components(separatedBy: ",")
        })
    }
}
