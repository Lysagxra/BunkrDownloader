"""Main module to read Bunkr URLs from a file and download from them."""

import asyncio
import os
import sys
from argparse import Namespace

from downloader import parse_arguments, validate_and_download
from src.bunkr_utils import get_bunkr_status
from src.config import SESSION_LOG, URLS_FILE, resolve_download_path
from src.file_utils import create_urls_file_backup, read_file, write_file
from src.general_utils import check_python_version, clear_terminal
from src.managers.live_manager import initialize_managers

async def process_urls(urls: list[str], args: Namespace, download_path: str) -> None:
    """Validate and downloads items for a list of URLs."""
    bunkr_status = get_bunkr_status()
    live_manager = initialize_managers(disable_ui=args.disable_ui)

    with live_manager.live:
        for url in urls:
            await validate_and_download(
                bunkr_status, 
                url, 
                live_manager, 
                args=args, 
                download_path=download_path
            )
        live_manager.stop()

async def main() -> None:
    """Bulk URL entry point."""
    clear_terminal()
    write_file(SESSION_LOG)
    check_python_version()
    
    args = parse_arguments(common_only=True)
    final_download_path = resolve_download_path(args)

    # Pre-create the root folder
    os.makedirs(final_download_path, exist_ok=True)
    create_urls_file_backup()

    urls = [url.strip() for url in read_file(URLS_FILE) if url.strip()]
    await process_urls(urls, args, final_download_path)

    # Clean up URLs file after success
    write_file(URLS_FILE)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)