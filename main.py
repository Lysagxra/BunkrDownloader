"""Main module to read Bunkr URLs from a file, and download from them.

Usage:
    To run the module, execute the script directly. It will process URLs listed in
    'URLs.txt' and log the session activities in 'session_log.txt'.
"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

from downloader import parse_arguments
from src.config import URLS_FILE
from src.file_utils import create_urls_file_backup, log_session_start, read_file
from src.general_utils import check_python_version, clear_terminal
from src.run_utils import (
    build_rate_limiter,
    inspect_urls,
    log_failed_urls,
    run_concurrent,
    run_sequential,
)

if TYPE_CHECKING:
    from argparse import Namespace


async def process_urls(urls: list[str], args: Namespace) -> list[str]:
    """Validate and download items for a list of URLs."""
    # Placeholder for integrating the Bunkr status endpoint when available
    bunkr_status: dict[str, str] = {}

    # Dry-run skips downloads and bypasses Live UI, printing a preview per URL
    if getattr(args, "dry_run", False):
        return await inspect_urls(urls, bunkr_status, args)

    # Shared RateLimiter ensures --rate-limit applies across all concurrent downloads
    rate_limiter = build_rate_limiter(args)
    max_concurrent = getattr(args, "max_concurrent_urls", 1) or 1

    # Process sequentially when concurrency is disabled or there is only one URL
    if max_concurrent <= 1 or len(urls) <= 1:
        return await run_sequential(urls, bunkr_status, args, rate_limiter)

    # Rich progress assumes only one active album. Use plain logging in concurrent mode
    # to prevent overlapping or corrupted progress displays
    return await run_concurrent(urls, bunkr_status, args, rate_limiter)


async def main() -> None:
    """Run the script and process URLs."""
    # Start with a clean terminal while preserving the existing logs
    clear_terminal()
    log_session_start()

    # Check the Python version and parse arguments
    check_python_version()
    args = parse_arguments(common_only=True)

    # Backup the URLs file
    create_urls_file_backup()

    # Read and process URLs, ignoring empty lines
    urls = [url.strip() for url in read_file(URLS_FILE) if url.strip()]
    failed_urls = await process_urls(urls, args)

    # Keep URLs.txt unchanged so completed items can be skipped and report failures
    if failed_urls:
        log_failed_urls(failed_urls)


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        sys.exit(1)
