"""Preview mode for --dry-run: resolve filenames and sizes without downloading.

Performs the same crawl/resolve/filter steps as a real download (page fetch, signed-URL
resolution, --ignore/--include filtering, on-disk and cached-state existence checks) but
never calls MediaDownloader and never writes any downloaded content to disk.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from rich.table import Table

from src.config import DOWNLOAD_HEADERS, KB, MAX_WORKERS, ResolveContext
from src.crawlers.crawler_utils import get_download_info
from src.downloaders.download_utils import detect_range_support
from src.file_utils import (
    matches_ignore_list,
    matches_include_list,
    reserve_unique_filename,
    truncate_filename,
)
from src.general_utils import fetch_page

if TYPE_CHECKING:
    from argparse import Namespace

    from rich.console import Console

    from src.config import SessionInfo

_STATUS_LABELS: dict[str, tuple[str, str]] = {
    "would_download": ("Would download", "green"),
    "already_downloaded": ("Already downloaded", "dim"),
    "filtered_ignore": ("Filtered (ignore list)", "yellow"),
    "filtered_include": ("Filtered (include list)", "yellow"),
    "unresolved": ("Could not resolve URL", "red"),
    "fetch_failed": ("Failed to fetch page", "red"),
}


def _format_size(num_bytes: int | None) -> str:
    """Format a byte count as a human-readable size string."""
    if num_bytes is None:
        return "unknown"
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < KB:
            return f"{value:.1f} {unit}"

        value /= KB

    return f"{value:.1f} TB"


def _get_filter_status(filename: str, args: Namespace) -> str | None:
    """Return the filter status for a filename based on CLI arguments."""
    ignore_list = getattr(args, "ignore", None) if args else None
    include_list = getattr(args, "include", None) if args else None

    if matches_ignore_list(filename, ignore_list):
        return "filtered_ignore"

    if matches_include_list(filename, include_list):
        return "filtered_include"

    return None


def _get_cached_result(
    item_page: str,
    context: ResolveContext,
) -> dict | None:
    """Return the cached result if the item has already been downloaded."""
    cached = context.cached_items.get(item_page)
    if not cached or cached.get("status") != "completed":
        return None

    filename = cached.get("filename", "")
    file_path = Path(context.session_info.download_path) / truncate_filename(filename)
    if not file_path.exists():
        return None

    return {
        "filename": filename,
        "size": file_path.stat().st_size,
        "status": "already_downloaded",
    }


async def _resolve_item(item_page: str, context: ResolveContext) -> dict:
    """Resolve filename, size and status for one item without downloading it."""
    async with context.semaphore:
        cached_result = _get_cached_result(item_page, context)
        if cached_result:
            return cached_result

        item_soup = await fetch_page(item_page)
        if item_soup is None:
            return {"filename": item_page, "size": None, "status": "fetch_failed"}

        download_link, filename, _item_date = await get_download_info(
            item_page, item_soup, clean_name=context.session_info.args.clean_name,
        )
        if not download_link:
            return {"filename": filename, "size": None, "status": "unresolved"}

        if context.session_info.args.clean_name:
            async with context.reservation_lock:
                filename = reserve_unique_filename(
                    filename,
                    context.reserved_names,
                )
                context.reserved_names.add(filename)

        filter_status = _get_filter_status(filename, context.session_info.args)
        if filter_status:
            return {"filename": filename, "size": None, "status": filter_status}

        final_path = (
            Path(context.session_info.download_path) / truncate_filename(filename)
        )
        if final_path.exists():
            return {
                "filename": filename,
                "size": final_path.stat().st_size,
                "status": "already_downloaded",
            }

        _, content_length = await asyncio.to_thread(
            detect_range_support,
            download_link,
            DOWNLOAD_HEADERS,
        )
        size = content_length if content_length and content_length > 0 else None
        return {"filename": filename, "size": size, "status": "would_download"}


def process_results_rows(results: list[dict], table: Table) -> tuple[int, dict]:
    """Update table rows and aggregate stats from results."""
    total_download_bytes = 0
    counts: dict[str, int] = {}

    for item in results:
        status = item["status"]
        counts[status] = counts.get(status, 0) + 1

        if status == "would_download" and item["size"]:
            total_download_bytes += item["size"]

        label, color = _STATUS_LABELS.get(status, (status, "white"))
        table.add_row(
            item["filename"] or "(unknown)",
            _format_size(item["size"]),
            f"[{color}]{label}[/{color}]",
        )

    return total_download_bytes, counts


async def execute_dry_run(
    album_id: str,
    item_pages: list[str],
    session_info: SessionInfo,
    cached_items: dict[str, dict],
    item_dates: dict[str, object],
    console: Console,
) -> None:
    """Print a preview table of what a download would do, without downloading."""
    semaphore = asyncio.Semaphore(MAX_WORKERS)
    reserved_names: set[str] = set()
    reservation_lock = asyncio.Lock()
    context = ResolveContext(
        session_info=session_info,
        cached_items=cached_items,
        item_dates=item_dates,
        semaphore=semaphore,
        reserved_names=reserved_names,
        reservation_lock=reservation_lock,
    )
    results = await asyncio.gather(
        *(_resolve_item(item_page, context) for item_page in item_pages),
    )

    table = Table(title=f"Dry run — {album_id} ({len(item_pages)} item(s))")
    table.add_column("Filename", overflow="fold")
    table.add_column("Size", justify="right")
    table.add_column("Status")
    total_download_bytes, counts = process_results_rows(results, table)

    console.print(table)
    console.print(
        f"\nWould download: {counts.get('would_download', 0)} file(s), "
        f"{_format_size(total_download_bytes)} total",
    )

    if counts.get("already_downloaded"):
        console.print(f"Already downloaded: {counts['already_downloaded']} file(s)")

    filtered = counts.get("filtered_ignore", 0) + counts.get("filtered_include", 0)
    if filtered:
        console.print(f"Filtered out: {filtered} file(s)")

    unresolved = counts.get("unresolved", 0) + counts.get("fetch_failed", 0)
    if unresolved:
        console.print(f"[red]Could not resolve: {unresolved} file(s)[/red]")
