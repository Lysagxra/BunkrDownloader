"""Main module to read Bunkr URLs from a file, and download from them.

This module manages the entire download process by leveraging asynchronous operations,
allowing for efficient handling of multiple URLs.

Usage:
    To run the module, execute the script directly. It will process URLs listed in
    'URLs.txt' and log the session activities in 'session_log.txt'.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

from downloader import parse_arguments, run_dry_run_for_url, validate_and_download
from src.bunkr_utils import get_bunkr_status
from src.config import SESSION_LOG, URLS_FILE
from src.file_utils import create_urls_file_backup, read_file
from src.general_utils import check_python_version, clear_terminal
from src.managers.live_manager import initialize_managers
from src.rate_limiter import RateLimiter

if TYPE_CHECKING:
    from src.managers.live_manager import LiveManager


async def _process_one_url(
    bunkr_status: dict[str, str],
    url: str,
    live_manager: LiveManager,
    args: Namespace,
    rate_limiter: RateLimiter,
) -> bool:
    """Run validate_and_download for one URL with a last-resort safety net.

    Returns:
        True if the URL ended with a permanent failure, False otherwise.
        An unexpected exception here is treated as a failure rather than
        propagating, so one bad URL never aborts the rest of the batch.
    """
    try:
        return await validate_and_download(
            bunkr_status, url, live_manager, args=args, rate_limiter=rate_limiter,
        )
    except KeyboardInterrupt:
        raise
    except Exception:  # noqa: BLE001 - last-resort safety net
        logging.exception("Unexpected error while processing %s", url)
        return True


async def process_urls(urls: list[str], args: Namespace) -> list[str]:
    """Validate and download items for a list of URLs.

    Returns:
        The subset of `urls` that ended with a permanent failure, so the
        caller can keep them in URLs.txt for an easy retry instead of
        silently discarding them.
    """
    bunkr_status = get_bunkr_status()

    if getattr(args, "dry_run", False):
        # Dry-run never downloads anything, so it runs outside the Live
        # progress UI entirely — one preview table per URL, printed plainly.
        console = Console()
        for url in urls:
            await run_dry_run_for_url(bunkr_status, url, args, console)
        return []

    # One RateLimiter shared across every URL in this batch, so --rate-limit
    # caps total bandwidth even when multiple files/connections across
    # different URLs are downloading concurrently.
    rate_limit_kb = getattr(args, "rate_limit", None)
    rate_limiter = RateLimiter(rate_limit_kb * 1024 if rate_limit_kb else None)

    max_concurrent = getattr(args, "max_concurrent_urls", 1) or 1

    if max_concurrent <= 1 or len(urls) <= 1:
        # Default, fully sequential path — unchanged from prior behavior.
        live_manager = initialize_managers(disable_ui=args.disable_ui)
        failed_urls = []

        with live_manager.live:
            for url in urls:
                had_failure = await _process_one_url(
                    bunkr_status, url, live_manager, args, rate_limiter,
                )
                if had_failure:
                    failed_urls.append(url)

            live_manager.stop()

        return failed_urls

    # Concurrent path: the Rich progress UI's overall-task tracking assumes
    # one album is in flight at a time (see ProgressManager._update_overall_task,
    # which always advances the *most recently added* overall task — correct
    # for sequential processing, but it would silently advance the wrong
    # album's progress bar if multiple albums were live simultaneously).
    # Rather than risk a corrupted/garbled display, concurrent mode always
    # falls back to plain log-line output instead of the live progress bars.
    live_manager = initialize_managers(disable_ui=True)
    if not args.disable_ui:
        live_manager.update_log(
            event="Concurrent mode",
            details=(
                f"Processing up to {max_concurrent} URL(s) concurrently — "
                "live progress bars are disabled in this mode (plain log "
                "lines are used instead) since they only support tracking "
                "one album at a time."
            ),
        )

    semaphore = asyncio.Semaphore(max_concurrent)

    async def _bounded(url: str) -> tuple[str, bool]:
        async with semaphore:
            had_failure = await _process_one_url(
                bunkr_status, url, live_manager, args, rate_limiter,
            )
            return url, had_failure

    with live_manager.live:
        results = await asyncio.gather(*(_bounded(url) for url in urls))
        live_manager.stop()

    return [url for url, had_failure in results if had_failure]


async def main() -> None:
    """Run the script and process URLs."""
    # Clear the terminal, but append a session marker to the log instead of
    # wiping it — previous runs' failure history stays available for review.
    clear_terminal()
    session_start = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with Path(SESSION_LOG).open("a", encoding="utf-8") as log_file:
        log_file.write(f"\n--- Session started {session_start} UTC ---\n")

    # Check Python version and parse arguments
    check_python_version()
    args = parse_arguments(common_only=True)

    # Backup the URLs file
    create_urls_file_backup()

    # Read and process URLs, ignoring empty lines
    urls = [url.strip() for url in read_file(URLS_FILE) if url.strip()]
    failed_urls = await process_urls(urls, args)

    # URLs.txt is left untouched — nothing is removed from it, successful
    # or not. Already-downloaded files are skipped automatically next run,
    # so re-running the same file is safe. Failed URLs are just reported
    # here for visibility.
    if failed_urls:
        print(f"\n{len(failed_urls)} URL(s) failed and may need attention:")
        for url in failed_urls:
            print(f"  - {url}")


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        sys.exit(1)
