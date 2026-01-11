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
├── downloader.py            # Module for initiating downloads from specified Bunkr URLs
├── main.py                  # Main script to run the downloader
├── URLs.txt                 # Text file listing album URLs to be downloaded
└── session_log.txt          # Log file for recording session details
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
python3 downloader.py <bunkr_url>
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

The Ignore List is specified using the `--ignore` argument in the command line.
This allows you to skip the download of any file from an album if its filename contains at least one of the specified strings in the list.
Item in the list should be separated by a space.

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

The Include List is specified using the `--include` argument in the command line.
This allows you to download a file from an album only if its filename contains at least one of the specified strings in the list.
Items in the list should be separated by a space.

### Usage

```bash
python3 downloader.py <bunkr_album_url> --include <include_list>
```

### Example

```bash
python3 downloader.py https://bunkr.si/a/PUK068QE --include FullSizeRender
```

## Batch Download

To batch download from multiple URLs, you can use the `main.py` script.
This script reads URLs from a file named `URLs.txt` and downloads each one using the media downloader.

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
python3 main.py
```

## File Download Location

If the `--custom-path <custom_path>` argument is used, the downloaded files will be saved in `<custom_path>/Downloads`.
Otherwise, the files will be saved in a `Downloads` folder created within the script's directory

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

## Maximum Number of Retries

When the download fails, by default there is 5 retry attempts to download each media file again.
You can control the number of maximum attempts with the `--max-retries` argument.
It may be useful when you would like to skip broken media faster for the very large media collection.

### Usage

Allowed values: 0 (don't re-download) and larger.

```bash
python3 downloader.py <bunkr_url> --max-retries 3
```

### Example:

```bash
python3 downloader.py https://bunkr.si/a/PUK068QE --max-retries 3
```

## Logging

The application logs any issues encountered during the download process in a file named `session.log`.
Check this file for any URLs that may have been blocked or had errors.
