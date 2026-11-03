# Bunkr for macOS

A native SwiftUI desktop application wrapping the existing Python downloader. The app bundles its Python runtime and dependencies; opening the built app requires no Terminal or Python installation.

## Build and open

Build on the Mac architecture you intend to run on. Requires Swift 6 / Apple Command Line Tools and Python 3.11 or newer for the build only:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r macos/requirements-build.txt
./scripts/build-macos.sh
open dist/Bunkr.app
```

Build with the macOS 27 SDK and run on macOS 27 or later. The Swift package, bundled executable and app metadata all target macOS 27. The local bundle is ad-hoc signed. Public distribution requires Developer ID signing and notarization.

The build script uses the selected macOS SDK. The test script runs the same native test methods with a standalone harness when only Command Line Tools are available. With a working Xcode/SwiftPM installation, `swift test --package-path macos` also runs them through XCTest.

Open `macos/Package.swift` in Xcode to edit the frontend. Running the unbundled Swift executable alone displays “Engine missing”; use the build script for a functional app.

## Use

1. Paste Bunkr album/file links, one per line, or import a UTF-8 text file.
2. Choose a download folder. New queue entries capture the current settings.
3. Add to Queue, then Start Queue (Command-R).
4. Select a row to see activity, or right-click for retry, copy link, folder, and removal actions.

The queue processes one URL at a time. The existing engine downloads up to three album files concurrently, with configurable connections per large file. The interface reports received bytes and known-size transfer progress separately from file counts. Unknown-size transfers stay indeterminate. Completed and intentionally skipped files are counted separately. Failed/unavailable files cause the URL to require attention.

Stop (Command-period) stops the current worker and leaves subsequent entries queued. Retry reuses completed files and the engine's complete saved chunks. Incomplete chunks and small streaming downloads may restart. Quitting during a download asks whether to stop and waits for the worker to exit. Interrupted entries require an explicit retry after relaunch; the queue never starts itself on launch.

Settings include original filenames, album folders, download attempts, connection count, aggregate speed limit, and comma-separated case-sensitive include/exclude filters. Include is an “any match” filter; Exclude takes precedence. Blank filters allow all files. The engine's low-disk-space check remains enabled.

## Data and architecture

- Queue, settings, and recent activity: `~/Library/Application Support/Bunkr/queue.json`.
- Diagnostics: `~/Library/Application Support/Bunkr/engine.log` rotates at 1 MiB with one backup. Export Diagnostics redacts signing query parameters. The Python engine also maintains `session.log`.
- Media, cached album state, and resumable chunks: the selected destination.
- Removing a queue entry or clearing finished entries does not delete downloaded files.
- Saved queue writes are atomic. Unreadable/corrupt queues are preserved and persistence is disabled for that session, with an error shown.
- Logs contain URLs and filenames. No analytics or remote app service is added.

`macos/bridge.py` calls the existing Python downloader directly and emits newline-delimited JSON on stdout. The Swift app launches the bundled engine with `Process`, sends one JSON request via stdin, and drains output off the main thread. It requires both an explicit successful result and a zero exit code before marking a URL complete. There is no shell interpolation. The engine runs outside the App Sandbox so it can write to the selected folders.

Two small engine changes support the frontend: single-file downloads honor the selected attempt count, and chunk merges publish via an atomic rename so cancellation cannot leave an incomplete final file that a retry skips.

## Validation

```sh
.venv/bin/python -m unittest discover -s tests -v
./scripts/test-macos.sh
```

Python tests exercise URL/options validation, success/failure results, a real downloader file write with fixture network responses, progress accounting, and interrupted chunk assembly. Swift tests cover URL validation, queue restoration/corruption, request filters, subprocess completion ordering, missing success events, and cancellation without starting another job.

Live Bunkr service availability, API changes, and large-album transfers must be checked with user-selected links. Offline fixture tests do not establish live service compatibility.

The original project's GPL-3.0 license applies. The app includes the license and Python engine source; preserve the full repository source and dependency license obligations when distributing builds.


Preview resolves the first entered link with the current filters and folder settings. Refresh or change an option to update the rows. Closing the sheet cancels its worker. Use Search to find queue entries, and select a row to inspect activity in the resizable inspector. Export Diagnostics and Clear History are available in the toolbar.
