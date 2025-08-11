"""Main module to read Bunkr URLs from a file, and download from them.

This module manages the entire download process by leveraging asynchronous
operations, allowing for efficient handling of multiple URLs.

Usage:
    To run the module, execute the script directly. It will process URLs
    listed in 'URLs.txt' and log the session activities in 'session_log.txt'.
"""

import asyncio
import sys

from downloader import initialize_managers, parse_arguments, validate_and_download
from helpers.bunkr_utils import get_bunkr_status
from helpers.config import FILE, SESSION_LOG
from helpers.file_utils import (
    check_python_version,
    read_file,
    write_file,
)
from helpers.general_utils import clear_terminal


async def process_urls(urls: list[str], *, disable_ui: bool = False) -> None:
    """Validate and downloads items for a list of URLs."""
    bunkr_status = get_bunkr_status()
    live_manager = initialize_managers(disable_ui=disable_ui)

    try:
        with live_manager.live:
            for url in urls:
                await validate_and_download(bunkr_status, url, live_manager)

            live_manager.stop()

    except KeyboardInterrupt:
        sys.exit(1)


async def main() -> None:
    """Run the script and process URLs."""
    # Clear the terminal and session log file
    clear_terminal()
    write_file(SESSION_LOG)

    # Check Python version
    check_python_version()

    # Parse arguments to get disable_ui flag
    args = parse_arguments()

    # Read and process URLs
    urls = read_file(FILE)
    await process_urls(urls, disable_ui=args.disable_ui)

    # Clear URLs file
    write_file(FILE)


if __name__ == "__main__":
    asyncio.run(main())
