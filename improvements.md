# Bunkr Downloader improvements

Implemented for macOS 27 and iOS/iPadOS 27. Both applications use deployment target 27.0. The implementation and remaining validation for each original item are listed below.

| # | Improvement | Implementation | Remaining validation |
| --- | --- | --- | --- |
| 1 | Safe Mac chunk reuse | Strong ETag identifies saved plans, exact ordered coverage validates ranges, If-Match protects each request, and 206 plus Content-Range and ETag are required before writing. Servers without a strong validator use a single stream. | Large live objects and changing CDN validators |
| 2 | Streams without a size | Clean end of stream publishes unknown-length downloads atomically. Declared lengths still require an exact match. | Covered by complete and truncated stream fixtures |
| 3 | iOS background transfers | Named system session, durable task descriptions and completion receipts, relaunch reconciliation, cancellation, and one fresh-signature retry. Discovered album items persist before tasks begin. | Physical-device screen lock, suspension, termination and cancellation |
| 4 | Partial album recovery | Persist failures by item, continue healthy files, display individual errors and retry failed items while retaining completed output. | Covered by a three-item album with a failed middle item |
| 5 | iOS storage and Wi-Fi | HEAD metadata drives an available-capacity check. Wi-Fi-only is captured on each job and applied to media requests, with connectivity waiting enabled. | Real cellular-to-Wi-Fi transitions and low-storage device behavior |
| 6 | Resolver parity | Both test suites read fixtures/resolver.json for pagination, duplicate links, escaped CDN paths, signing fallback, missing files and challenge pages. | Expand corpus as service layouts evolve |
| 7 | Mac album preview | Structured preview bridge reuses the CLI resolver and filters, displays sizes and outcomes, refreshes on option changes and cancels its own worker on dismissal. Destination folders and media are untouched. | Hands-on composer and filter interaction |
| 8 | Desktop navigation | Native sidebar selection, searchable queue, resizable inspector, toolbar Start/Stop and keyboard-accessible retry controls. | VoiceOver, Increase Contrast and narrow-window review |
| 9 | iOS share sheet | Embedded share extension writes atomic App Group inbox entries. Foreground import validates and deduplicates links, then queues them for explicit start. | Signed device provisioning and Safari share-sheet flow |
| 10 | Mobile file discovery | Resolved titles are displayed independently of stable job directories. Quick Look, sharing and missing-file availability appear in details. | iPhone/iPad preview and external Files moves |
| 11 | Byte progress | Mac bridge emits absolute byte counters so retries replace earlier attempts. Both interfaces show received bytes and known-size progress separately from file counts. Unknown sizes stay indeterminate. | Mixed-size large live albums |
| 12 | Apple CI | Apple 27 workflow uses the xcode-27 runner for Python tests, Mac queue tests, shared resolver fixtures, desktop compilation and iOS/share-extension build. | GitHub execution after push |
| 13 | Mac diagnostics | Redacted stderr is drained into a rotating 1 MiB log and one backup. Export redacts signing parameters again. Clear History removes queue history without deleting media. | Rotation and signing-query redaction covered by the native harness |

## Local checks

- Eleven Python bridge, resolver and transfer-integrity tests.
- Nine native Mac tests, including subprocess lifecycle, diagnostic rotation and redaction.
- Six host-run mobile tests, including shared fixtures, same-name output, storage rejection, partial album retries and saved-file recovery.
- macOS 27 app build with bundled Python engine and code-signature verification.
- iOS 27 device and simulator compilation, including the embedded share extension.

Host-run fixtures exercise the mobile queue and foreground fixture transport. The actual iOS background session and share extension require the device checks below.

## Device release checklist

- [ ] Sign the app and extension with the same development team and enable group.com.bunkrdownloader.shared for both identifiers.
- [ ] Share the same Safari link twice, relaunch Bunkr and verify one queued job.
- [ ] Lock the screen during media transfer, switch apps and verify one complete output after returning.
- [ ] Terminate the app through the system and verify task reconciliation. Test explicit Stop and user force-quit separately.
- [ ] Let a signature expire while offline, reconnect and verify refreshed signing.
- [ ] Enable Wi-Fi-only, start on cellular and verify waiting followed by progress on Wi-Fi.
- [ ] Download near the storage limit and verify the actionable capacity error.
- [ ] Preview and share files on iPhone and iPad, then move a file in Files and verify availability updates.
- [ ] Review Dynamic Type, VoiceOver, Increase Contrast, narrow Mac windows and keyboard-only retry.
- [ ] Download a large mixed-size album and compare byte totals with saved output.

Apple documents the required background completion-handler lifecycle in its [background download guide](https://developer.apple.com/documentation/foundation/downloading-files-in-the-background). The CI runner comes from the [official Xcode 27 image](https://github.com/actions/runner-images/blob/main/images/macos/xcode-27-arm64-Readme.md).
