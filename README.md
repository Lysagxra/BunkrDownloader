# Bunkr Downloader

> A Python Bunkr downloader that fetches images and videos from URLs. It supports both Bunkr albums and individual file URLs, logs issues, and enables concurrent downloads for efficiency.

![Demo](https://github.com/Lysagxra/BunkrDownloader/blob/8d07aaa4fe4e5b438e9ccc75bf0b71c845df942d/assets/demo.gif)

## Features

- Downloads multiple files from an album concurrently.
- Supports [batch downloading](https://github.com/Lysagxra/BunkrDownloader?tab=readme-ov-file#batch-download) via a list of URLs.
- Supports [selective files downloading](https://github.com/Lysagxra/BunkrDownloader/tree/main?tab=readme-ov-file#selective-download) based on filename criteria.
- Supports [custom download location](https://github.com/Lysagxra/BunkrDownloader/tree/main?tab=readme-ov-file#file-download-location).
- Provides [minimal UI](https://github.com/Lysagxra/BunkrDownloader/tree/main?tab=readme-ov-file#disable-ui-for-notebooks) for notebook environments.
- Provides progress indication during downloads.
- Automatically creates a directory structure for organized storage.
- Logs URLs that encounter errors for troubleshooting.
- Supports HTTP resume for interrupted downloads (uses a `.temp` partial file and Range requests).
- Per-session retry lists and timestamped verbose logs for debugging.

## Dependencies

- Python 3
- `BeautifulSoup` (bs4) - for HTML parsing
- `requests` - for HTTP requests
- `rich` - for progress display in the terminal

<details>

<summary>Show directory structure</summary>

```
project-root/
├── helpers/
│ ├── crawlers/
| | ├── api_utils.py         # Utilities for handling API requests and responses
│ │ └── crawler_utils.py     # Utilities for extracting media download links
│ ├── downloaders/
│ │ ├── album_downloader.py  # Manages the downloading of entire albums
│ │ ├── download_utils.py    # Utilities for managing the download process
│ │ └── media_downloader.py  # Manages the downloading of individual media files
│ ├── managers/
│ │ ├── live_manager.py      # Manages a real-time live display
│ │ ├── log_manager.py       # Manages real-time log updates
│ │ └── progress_manager.py  # Manages progress bars
│ ├── bunkr_utils.py         # Utilities for checking Bunkr status
│ ├── config.py              # Manages constants and settings used across the project
│ ├── file_utils.py          # Utilities for managing file operations
│ ├── general_utils.py       # Miscellaneous utility functions
│ └── url_utils.py           # Utilities for Bunkr URLs
├── logs/                    # Timestamped verbose run logs (created when --verbose used)
├── session/                 # Per-session retry lists (stable when --session-id is provided)
├── downloader.py            # Module for initiating downloads from specified Bunkr URLs
├── main.py                  # Main script to run the downloader
└── URLs.txt                 # Text file listing album URLs to be downloaded
```

</details>

## Installation

1. Clone the repository:

```bash
git clone https://github.com/Lysagxra/BunkrDownloader.git
```

2. Navigate to the project directory:

```bash
cd BunkrDownloader
```

3. Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Single Download

To download a single media from an URL, you can use `downloader.py`, running the script with a valid album or media URL.

### Usage

```bash
python3 downloader.py <bunkr_url> [--verbose] [--retries N] [--session-id ID]
```

### Examples

You can either download an entire album or a specific file:

```
python3 downloader.py https://bunkr.si/a/PUK068QE       # Download album
python3 downloader.py https://bunkr.fi/f/gBrv5f8tAGlGW  # Download single media
```

## Selective Download

The script supports selective file downloads from an album, allowing you to exclude files using the [Ignore List](https://github.com/Lysagxra/BunkrDownloader?tab=readme-ov-file#ignore-list) and include specific files with the [Include List](https://github.com/Lysagxra/BunkrDownloader?tab=readme-ov-file#include-list).

## Ignore List

The Ignore List is specified using the `--ignore` argument in the command line. This allows you to skip the download of any file from an album if its filename contains at least one of the specified strings in the list. Item in the list should be separated by a space.

### Usage

```bash
python3 downloader.py <bunkr_album_url> --ignore <ignore_list>
```

### Example

This feature is particularly useful when you want to skip files with certain extensions, such as `.zip` files. For instance:

```bash
python3 downloader.py https://bunkr.si/a/PUK068QE --ignore .zip
```

## Include List

The Include List is specified using the `--include` argument in the command line. This allows you to download a file from an album only if its filename contains at least one of the specified strings in the list. Items in the list should be separated by a space.

### Usage

```bash
python3 downloader.py <bunkr_album_url> --include <include_list>
```

### Example

```bash
python3 downloader.py https://bunkr.si/a/PUK068QE --include FullSizeRender
```

## Batch Download

To batch download from multiple URLs, you can use the `main.py` script. This script reads URLs from a file named `URLs.txt` and downloads each one using the media downloader.

### Usage

1. Create a file named `URLs.txt` in the root of your project, listing each URL on a new line.

- Example of `URLs.txt`:

```
https://bunkr.si/a/PUK068QE
https://bunkr.fi/f/gBrv5f8tAGlGW
https://bunkr.fi/a/kVYLh49Q
```

- Ensure that each URL is on its own line without any extra spaces.
- You can add as many URLs as you need, following the same format.

2. Run the batch download script:

```
python3 main.py [--verbose] [--session-id ID]
```

## File Download Location

If the `--custom-path <custom_path>` argument is used, the downloaded files will be saved in `<custom_path>/Downloads`. Otherwise, the files will be saved in a `Downloads` folder created within the script's directory

### Usage

```bash
python3 main.py --custom-path <custom_path>
```

### Example

```bash
python3 main.py --custom-path /path/to/external/drive
```

## Disable UI for Notebooks

When the script is executed in a notebook environment (such as Jupyter), excessive output may lead to performance issues or crashes.

### Usage

You can run the script with the `--disable-ui` argument to disable the progress bar and minimize log messages.

To disable the UI, use the following command:

```
python3 main.py --disable-ui
```

To download a single file or album without the UI, you can use this command:

```bash
python3 downloader.py <bunkr_url> --disable-ui
```

## Logging

The downloader separates session retry lists from verbose run logs and provides the following CLI flags:

- `--session-id ID`: when provided the session retry list is created as `session/ID.txt`. This file is stable across runs so you can re-run the downloader and pick up the same retry list for the album or item.
- `--verbose`: duplicates UI log lines to a verbose log file under `logs/` and also outputs the session/verbose paths in the Log Messages header.
- `--retries N`: controls how many times the downloader will retry a failed file before writing it to the session retry list.

- Behavior details:
- Session retry lists live in `session/`.
	- If you don't provide `--session-id` a timestamped session file like `session/session_YYYYMMDD_HHMMSS.txt` is created.
	- When `--session-id ID` is used, the session file is `session/ID.txt` (no timestamp) so the file can be re-used across runs.
- Verbose logs live in `logs/` and are timestamped per run:
	- When `--session-id ID` is provided the verbose log is `logs/ID_YYYYMMDD_HHMMSS.log` (identifier + timestamp).
	- When no ID is provided the verbose log is `logs/verbose_YYYYMMDD_HHMMSS.log`.
- Failed download links are appended to the session file (duplicate URLs are deduplicated).
- Partial downloads are saved alongside the final filename with a `.temp` suffix and are resumed using HTTP Range where supported. If the server ignores Range, the partial is removed and the download restarts.

Example

```
python3 downloader.py https://bunkr.si/a/kVYLh49Q --session-id kVYLh49Q --verbose
```

This will create `session/kVYLh49Q.txt` and a verbose log such as `logs/kVYLh49Q_YYYYMMDD_HHMMSS.log`.

## Verbose logging (current behavior)

Note: the downloader now writes verbose/debug information only to a verbose log file and does not print debug traces to the console. This keeps the terminal output clean during large runs or automated executions.

- `--verbose` enables detailed run logging and tracebacks; those are written to the verbose log file under `logs/` (timestamped by default or derived from `--session-id`).
- Console output is intentionally minimal: the progress UI will show run progress, while detailed debug messages and exception tracebacks are recorded only in the verbose log.
- Log writes are flushed and fsynced immediately to reduce reordering and ensure visibility of entries when multiple threads write concurrently.

How to view verbose logs:

```bash
# tail the most recent verbose log (works when logs are timestamped)
tail -f logs/verbose_*.log

# or, if you provided --session-id, tail the specific file
tail -f logs/<your_session_id>_*.log
```

If you prefer the old behavior where `--verbose` prints debug output to the console, we can add an additional flag to re-enable console logging alongside the verbose file.

## Retry behavior (session file)

The downloader collects failed URLs into a per-session retry list so you can retry them automatically after the main download pass. Here's how it works:

- When a file reaches its configured retry limit (controlled with `--retries`), the URL is appended to the session file (under `session/`). Duplicate URLs are skipped.
- The session file path is resolved as `session/<name>.txt`. Use `--session-id ID` to create a stable file (`session/ID.txt`) you can re-run across multiple sessions; otherwise a timestamped file is created for each run.
- After the main download tasks complete, the script performs a single post-run retry pass over the session file while the live UI is still active. The retry pass:
	- Reads the session file and treats it as the authoritative list of deferred URLs.
	- Sets the UI to show `1/N, 2/N, ...` for the retry attempts so you can see progress within the retry list.
	- Attempts each URL once (regardless of previous per-file retry count). Successful retries are removed immediately from the session file so it always reflects remaining work.
	- Failed retries remain in the session file (they will be written back at the end of the pass). If all retries succeed, the session file is removed.

Notes:

- The retry pass runs only once per run. If you need more passes, you can re-run the script or we can make the number of retry passes configurable.
- Session-file updates are flushed and fsynced to disk to reduce the chance of lost entries during unexpected termination.
- The verbose log (use `--verbose`) contains detailed entries for the retry pass, including the resolved session path, counts read, and a completion summary.

## Session log path resolution

The downloader now standardizes how the session log path is resolved:

- If `SESSION_LOG` (internal config value) is an absolute path, that path is used directly.
- If `SESSION_LOG` is just a filename (default: `session.log`), it is placed under the default session directory: `session/<filename>`.
- Supplying `--session-id ID` assigns a filename (`ID.txt` or a timestamped variant when omitted) which is then resolved using the same rule above.
- Internally a helper resolves the effective path; other components no longer recompute `session/<name>` manually, reducing inconsistencies.

Implications:

- You can override the session log destination by setting `SESSION_LOG` to an absolute path before running (advanced usage).
- Tools and retry logic always operate on the resolved path; duplicate entries are avoided regardless of where the file lives.
- The default directory (`session/`) can be changed centrally in code (currently `"session"`) without modifying multiple call sites.

Example (default behavior):

```
python3 downloader.py https://bunkr.si/a/EXAMPLE --session-id EXAMPLE --verbose
# Effective session log: session/EXAMPLE.txt
# Effective verbose log: logs/EXAMPLE_YYYYMMDD_HHMMSS.log
```

Example (absolute override – advanced):

```python
import src.config as cfg
cfg.SESSION_LOG = "/tmp/custom_session_retry_list.txt"
# Then invoke the downloader script; session entries will append to /tmp/custom_session_retry_list.txt
```

If you do not need advanced overrides, continue using `--session-id` or omit it for timestamped files; the helper will handle placement automatically.

