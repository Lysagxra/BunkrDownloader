"""Main module to read Bunkr URLs from a file, and download from them.

This module manages the entire download process by leveraging asynchronous operations,
allowing for efficient handling of multiple URLs.

Usage:
    To run the module, execute the script directly. It will process URLs listed in
    'URLs.txt' and log the session activities in 'session_log.txt'.
"""

import asyncio
import sys
from argparse import Namespace

from downloader import parse_arguments, validate_and_download
from src.bunkr_utils import get_bunkr_status
from src.config import SESSION_LOG, URLS_FILE
from src.file_utils import read_file, write_file
from src.general_utils import check_python_version, clear_terminal
from src.managers.live_manager import initialize_managers


async def process_urls(urls: list[str], args: Namespace) -> None:
    """Validate and downloads items for a list of URLs."""
    bunkr_status = get_bunkr_status()
    live_manager = initialize_managers(disable_ui=args.disable_ui, verbose=args.verbose)

    with live_manager.live:
        for url in urls:
            await validate_and_download(bunkr_status, url, live_manager, args=args)

        # After the batch, perform a single retry pass over the session file so any
        # deferred URLs are attempted once more while the live UI is still active.
        try:
            from src.downloaders.retry_manager import run_session_retry_pass

            await run_session_retry_pass(live_manager)
        except Exception:
            pass

        live_manager.stop()


async def main() -> None:
    """Run the script and process URLs."""
    clear_terminal()

    # Check Python version and parse arguments
    check_python_version()
    args = parse_arguments(common_only=True)

    # Configure session log path according to optional session-id
    from src.file_utils import set_session_log_path

    set_session_log_path(args.session_id)

    if args.disable_ui:
        try:
            import importlib

            cfg = importlib.import_module("src.config")
            verbose_path = getattr(cfg, "VERBOSE_LOG", "")
            print(f"Starting batch downloads (verbose log: {verbose_path})", flush=True)
        except Exception:
            print("Starting batch downloads", flush=True)

    # Read and process URLs, ignoring empty lines
    urls = [url.strip() for url in read_file(URLS_FILE) if url.strip()]
    await process_urls(urls, args)

    # Clear URLs file
    write_file(URLS_FILE)

    # If session log is empty after the run, remove it
    try:
        import importlib
        from pathlib import Path

        cfg = importlib.import_module("src.config")
        session_file = Path(cfg.SESSION_LOG)
        if session_file.exists() and session_file.stat().st_size == 0:
            session_file.unlink()
    except Exception:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        sys.exit(1)
