"""Utilities for processing URL batches with sequential and concurrent execution."""

import asyncio
import logging
from argparse import Namespace

from rich.console import Console

from downloader import execute_url_dry_run, initialize_managers, validate_and_download
from src.config import KB
from src.managers.live_manager import LiveManager
from src.rate_limiter import RateLimiter


async def process_one_url(
    bunkr_status: dict[str, str],
    url: str,
    live_manager: LiveManager,
    args: Namespace,
    rate_limiter: RateLimiter,
) -> bool:
    """Run validate_and_download for one URL with a last-resort safety net.

    Returns:
        True if the URL ended with a permanent failure, False otherwise.

    """
    try:
        return await validate_and_download(
            bunkr_status,
            url,
            live_manager,
            args=args,
            rate_limiter=rate_limiter,
        )

    except Exception:
        logging.exception("Unexpected error while processing %s", url)
        return True


async def inspect_urls(
    urls: list[str], bunkr_status: dict[str, str], args: Namespace,
) -> list[str]:
    """Execute a dry-run preview for a list of URLs without downloading anything."""
    console = Console()
    for url in urls:
        await execute_url_dry_run(bunkr_status, url, args, console)

    return []


def build_rate_limiter(args: Namespace) -> RateLimiter:
    """Build a RateLimiter from CLI args (rate_limit in KB/s)."""
    rate_limit = getattr(args, "rate_limit", None)
    return RateLimiter(rate_limit * KB if rate_limit else None)


def build_live_manager(args: Namespace, *, force_disable: bool = False) -> LiveManager:
    """Initialize a LiveManager, optionally forcing UI disable."""
    return initialize_managers(
        disable_ui=force_disable or getattr(args, "disable_ui", False),
    )


async def run_sequential(
    urls: list[str],
    bunkr_status: dict[str, str],
    args: Namespace,
    rate_limiter: RateLimiter,
) -> list[str]:
    """Process URLs sequentially and return those that failed."""
    live_manager = build_live_manager(args)

    failed_urls: list[str] = []

    with live_manager.live:
        for url in urls:
            failed = await process_one_url(
                bunkr_status, url, live_manager, args, rate_limiter,
            )
            if failed:
                failed_urls.append(url)

        live_manager.stop()

    return failed_urls


async def run_concurrent(
    urls: list[str],
    bunkr_status: dict[str, str],
    args: Namespace,
    rate_limiter: RateLimiter,
) -> list[str]:
    """Process URLs concurrently and return those that failed."""
    live_manager = build_live_manager(args, force_disable=True)

    if not args.disable_ui:
        live_manager.update_log(
            event="Concurrent mode",
            details=(
                f"Processing up to {args.max_concurrent_urls} URL(s) concurrently — "
                "progress bars disabled (logging mode only)."
            ),
        )

    semaphore = asyncio.Semaphore(args.max_concurrent_urls or 1)

    async def _bounded(url: str) -> tuple[str, bool]:
        async with semaphore:
            failed = await process_one_url(
                bunkr_status, url, live_manager, args, rate_limiter,
            )
            return url, failed

    with live_manager.live:
        results = await asyncio.gather(*(_bounded(url) for url in urls))
        live_manager.stop()

    return [url for url, failed in results if failed]

def log_failed_urls(failed_urls: list[str]) -> None:
    """Log a summary and list of failed URLs."""
    logging.warning("\n%d URL(s) failed and may need attention:", len(failed_urls))
    for url in failed_urls:
        logging.warning(url)
