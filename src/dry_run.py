"""Preview mode for --dry-run: resolve filenames and sizes without downloading.

Performs the same crawl/resolve/filter steps as a real download (page
fetch, signed-URL resolution, --ignore/--include filtering, on-disk and
cached-state existence checks) but never calls MediaDownloader and never
writes any downloaded content to disk.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

from src.config import DOWNLOAD_HEADERS, MAX_WORKERS
from src.crawlers.crawler_utils import get_download_info
from src.downloaders.download_utils import detect_range_support
from src.file_utils import matches_ignore_list, matches_include_list, truncate_filename
from src.general_utils import fetch_page

if TYPE_CHECKING:
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
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


async def _resolve_item(
    item_page: str,
    session_info: SessionInfo,
    cached_items: dict[str, dict],
    semaphore: asyncio.Semaphore,
) -> dict:
    """Resolve filename, size and status for one item without downloading it."""
    async with semaphore:
        cached = cached_items.get(item_page)
        if cached and cached.get("status") == "completed":
            filename = cached.get("filename", "")
            expected_path = (
                Path(session_info.download_path) / truncate_filename(filename)
            )
            if expected_path.exists():
                return {
                    "filename": filename,
                    "size": expected_path.stat().st_size,
                    "status": "already_downloaded",
                }
            # Cached "completed" entry is stale (file missing) — fall
            # through and resolve it fresh, same as a real download would.

        item_soup = await fetch_page(item_page)
        if item_soup is None:
            return {"filename": item_page, "size": None, "status": "fetch_failed"}

        download_link, filename = await get_download_info(item_page, item_soup)
        if not download_link:
            return {"filename": filename, "size": None, "status": "unresolved"}

        args = session_info.args
        ignore_list = getattr(args, "ignore", None) if args else None
        include_list = getattr(args, "include", None) if args else None

        if matches_ignore_list(filename, ignore_list):
            return {"filename": filename, "size": None, "status": "filtered_ignore"}
        if matches_include_list(filename, include_list):
            return {"filename": filename, "size": None, "status": "filtered_include"}

        final_path = Path(session_info.download_path) / truncate_filename(filename)
        if final_path.exists():
            return {
                "filename": filename,
                "size": final_path.stat().st_size,
                "status": "already_downloaded",
            }

        _, content_length = await asyncio.to_thread(
            detect_range_support, download_link, DOWNLOAD_HEADERS,
        )
        size = content_length if content_length and content_length > 0 else None
        return {"filename": filename, "size": size, "status": "would_download"}


async def run_dry_run(
    album_id: str,
    item_pages: list[str],
    session_info: SessionInfo,
    cached_items: dict[str, dict],
    console: Console,
    max_workers: int = MAX_WORKERS,
) -> None:
    """Print a preview table of what a download would do, without downloading.

    Args:
        album_id: Album identifier (or single-item identifier) used as the
            table title.
        item_pages: The item page URLs that would be processed.
        session_info: Session context (download path, args, etc.).
        cached_items: Per-item state persisted from a previous run, used to
            report "already downloaded" without a network round-trip.
        console: Rich console to print the report to.
        max_workers: Concurrency limit for resolving items, matching the
            same default used by real album downloads.
    """
    semaphore = asyncio.Semaphore(max_workers)
    results = await asyncio.gather(
        *(_resolve_item(p, session_info, cached_items, semaphore) for p in item_pages),
    )

    table = Table(title=f"Dry run — {album_id} ({len(item_pages)} item(s))")
    table.add_column("Filename", overflow="fold")
    table.add_column("Size", justify="right")
    table.add_column("Status")

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

    console.print(table)
    console.print(
        f"\nWould download: {counts.get('would_download', 0)} file(s), "
        f"{_format_size(total_download_bytes)} total",
    )
    if counts.get("already_downloaded"):
        console.print(f"Already downloaded: {counts['already_downloaded']} file(s)")

    filtered_total = counts.get("filtered_ignore", 0) + counts.get("filtered_include", 0)
    if filtered_total:
        console.print(f"Filtered out: {filtered_total} file(s)")

    unresolved_total = counts.get("unresolved", 0) + counts.get("fetch_failed", 0)
    if unresolved_total:
        console.print(f"[red]Could not resolve: {unresolved_total} file(s)[/red]")
