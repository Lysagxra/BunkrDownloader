"""Module that facilitates the downloading of entire Bunkr albums.

This module provides features for managing progress, handling failed downloads, and
integrating with live task displays.
"""
from __future__ import annotations

import asyncio
from asyncio import Semaphore
from pathlib import Path
from typing import TYPE_CHECKING

from src.config import MAX_RETRIES, MAX_WORKERS
from src.crawlers.crawler_utils import get_download_info
from src.enums import FailedReason, SkippedReason
from src.managers.state_manager import save_album_state
from src.misc.file_utils import reserve_unique_filename, truncate_filename
from src.misc.general_utils import fetch_page
from src.models import (
    AlbumInfo,
    DownloadInfo,
    DownloadState,
    ItemInfo,
    RetryConfig,
    SessionInfo,
)

from .media_downloader import MediaDownloader

if TYPE_CHECKING:
    from src.managers.live_manager import LiveManager

_FETCH_BASE_DELAY = 1.5


class AlbumDownloader:
    """Manage the downloading of entire Bunkr albums."""

    def __init__(
        self,
        session_info: SessionInfo,
        album_info: AlbumInfo,
        live_manager: LiveManager,
        cached_items: dict[str, dict] | None = None,
    ) -> None:
        """Initialize the AlbumDownloader instance."""
        self.session_info = session_info
        self.album_info = album_info
        self.live_manager = live_manager
        # State persisted from a previous run, used to skip completed items without
        # making a network request.
        self.download_state = DownloadState(cached_items=dict(cached_items or {}))
        self._state_lock = asyncio.Lock()
        self._reserved_filenames: set[str] = set()

    async def execute_item_download(
        self,
        item_page: str,
        current_task: int,
        semaphore: Semaphore,
        max_retries: int,
    ) -> None:
        """Handle the download of an individual item in the album."""
        async with semaphore:
            # Fast path: previously downloaded and still on disk -- skip the item page
            # and signing API.
            if await self._skip_cached_item(item_page, current_task):
                return

            # Cached file is missing or stale -- fall through and process normally.
            task = self.live_manager.add_task(current_task=current_task)

            # Process the download of an item
            item_info = await self._resolve_item_download(item_page)
            if item_info.download_link:
                await self._download_item(item_info, task, max_retries)

            else:
                # URL could not be resolved after all retries -- report as failed.
                # No download link remains to retry, so treat it as permanent.
                item_filename = item_info.filename
                self.live_manager.update_log(
                    event="Download failed",
                    details=f"Could not resolve a download URL for {item_filename}.",
                )
                self.live_manager.update_task(task, completed=100, visible=False)
                self.live_manager.update_summary(FailedReason.MAX_RETRIES_REACHED)
                self.download_state.unresolved_failures += 1
                await self._persist_item_state(item_page, item_filename, failed=True)

    async def download_album(
        self,
        max_workers: int = MAX_WORKERS,
        max_retries: int = MAX_RETRIES,
    ) -> bool:
        """Handle the album download.

        Returns:
            True if at least one item permanently failed after the extra retry pass;
            False if every item either succeeded or was intentionally skipped.

        """
        num_tasks = len(self.album_info.item_pages)
        self.live_manager.add_overall_task(
            description=self.album_info.album_id,
            num_tasks=num_tasks,
        )

        # Create tasks for downloading each item in the album
        semaphore = asyncio.Semaphore(max_workers)
        tasks = [
            self.execute_item_download(item_page, current_task, semaphore, max_retries)
            for current_task, item_page in enumerate(self.album_info.item_pages)
        ]
        await asyncio.gather(*tasks)

        # If there are failed downloads, process them after all downloads are complete
        still_failed = (
            await self._process_failed_downloads()
            if self.download_state.failed_downloads else []
        )
        return bool(still_failed) or self.download_state.unresolved_failures > 0

    # Private methods
    async def _skip_cached_item(self, item_page: str, current_task: int) -> bool:
        """Skip an item if its cached download is still present on disk."""
        cached = self.download_state.cached_items.get(item_page)
        if not cached or cached.get("status") != "completed":
            return False

        filename = cached.get("filename", "")
        expected_path = (
            Path(self.session_info.download_path)
            / truncate_filename(filename)
        )
        if not expected_path.exists():
            return False

        task = self.live_manager.add_task(current_task=current_task)
        self.live_manager.update_log(
            event="Skipped download",
            details=(
                f"{filename} has already been downloaded (cached from a previous run)."
            ),
        )
        self.live_manager.update_task(task, completed=100, visible=False)
        self.live_manager.update_summary(SkippedReason.ALREADY_DOWNLOADED)
        return True

    async def _resolve_item_download(self, item_page: str) -> ItemInfo:
        """Resolve the download URL, filename and date for an item page."""
        item_soup = await self._fetch_page_with_retries(item_page)
        item_download_link, item_filename, page_item_date = await get_download_info(
            item_page,
            item_soup,
            clean_name=self.session_info.args.clean_name,
        )
        if self.session_info.args.clean_name:
            item_filename = await self._reserve_filename_for_item(
                item_filename,
                item_page,
            )

        # Prefer the date read from the album listing page (confirmed reliable); fall
        # back to whatever get_download_info found on the item's own page.
        item_date = self.album_info.item_dates.get(item_page) or page_item_date
        return ItemInfo(
            page=item_page,
            filename=item_filename,
            download_link=item_download_link,
            date=item_date,
        )

    async def _download_item(
        self,
        item_info: ItemInfo,
        task: int,
        max_retries: int,
    ) -> None:
        """Download an item and persist its resulting download state."""
        download_info = DownloadInfo(
            item_url=item_info.page,
            download_link=item_info.download_link,
            filename=item_info.filename,
            task=task,
            item_date=item_info.date,
        )
        retry_confing = RetryConfig(retries=max_retries, has_external_retry=True)
        media_downloader = MediaDownloader(
            session_info=self.session_info,
            download_info=download_info,
            live_manager=self.live_manager,
            retry_config=retry_confing,
        )

        failed_download = await asyncio.to_thread(media_downloader.download)
        if failed_download:
            self.download_state.failed_downloads.append({
                "id": task,
                "filename": item_info.filename,
                "download_link": item_info.download_link,
                "item_url": item_info.page,
                "item_date": item_info.date,
            })

        await self._persist_item_state(
            item_info.page,
            item_info.filename,
            failed=failed_download,
        )

    async def _persist_item_state(
        self, item_page: str,
        filename: str,
        *,
        failed: bool,
    ) -> None:
        """Record this item's outcome and persist the album state to disk.

        Marks the item "completed" only when the download did not fail AND the file is
        verifiably present on disk -- this stays accurate regardless of why the download
        call returned success (a fresh download, an already-existed skip, or an
        offline-domain skip all funnel through here).
        """
        is_completed = False
        if not failed:
            expected_path = (
                Path(self.session_info.download_path) / truncate_filename(filename)
            )
            is_completed = expected_path.exists()

        async with self._state_lock:
            self.download_state.cached_items[item_page] = {
                "filename": filename,
                "status": "completed" if is_completed else "failed",
            }
            save_album_state(
                self.session_info.download_path,
                self.album_info.album_id,
                self.album_info.item_pages,
                self.download_state.cached_items,
                self.album_info.item_dates,
            )

    async def _reserve_filename_for_item(self, filename: str, item_page: str) -> str:
        """Reserve an unique filename for this album run.

        Prevents concurrent tasks from selecting the same '(N)' candidate when multiple
        items share the same original filename. When a previous run already assigned a
        name to this exact item, that name is reused, so the already-downloaded check
        keeps matching even though items are resolved in a non-deterministic order.
        """
        async with self._state_lock:
            cached_filename = (
                self.download_state.cached_items.get(item_page) or {}
            ).get("filename")
            unique_filename = (
                cached_filename
                if cached_filename and cached_filename not in self._reserved_filenames
                else reserve_unique_filename(filename, self._reserved_filenames)
            )
            self._reserved_filenames.add(unique_filename)
            return unique_filename

    async def _fetch_page_with_retries(
        self,
        item_page: str,
        max_retries: int = MAX_RETRIES,
        base_delay: float = _FETCH_BASE_DELAY,
    ) -> None:
        """Try to fetch a page multiple times with progressive backoff."""
        item_soup = None
        for attempt in range(1, max_retries + 1):
            item_soup = await fetch_page(item_page)
            if item_soup is not None:
                return item_soup

            self.live_manager.update_log(
                event="Fetch retry",
                details=f"Attempt {attempt}/{max_retries} failed for: {item_page}",
            )
            if attempt < max_retries:
                await asyncio.sleep(base_delay * attempt)

        # All attempts failed
        self.live_manager.update_log(
            event="Fetch failed",
            details=f"Unable to load page after {max_retries} attempts: {item_page}",
        )
        error_message = f"Failed to load page: {item_page}"
        raise RuntimeError(error_message)

    async def _retry_failed_download(self, failed_download_info: DownloadInfo) -> bool:
        """Retry a single failed download once. Returns True if it failed again."""
        media_downloader = MediaDownloader(
            session_info=self.session_info,
            download_info=failed_download_info,
            live_manager=self.live_manager,
            # Retry once for failed downloads. No external retries are available after
            # this attempt.
            retry_config=RetryConfig(retries=1, has_external_retry=False),
        )
        # Run the synchronous download function in a separate thread
        return await asyncio.to_thread(media_downloader.download)

    async def _process_failed_downloads(self) -> list[dict]:
        """Retry every failed download once more.

        Returns:
            The subset of failed_downloads that permanently failed again on this retry.

        """
        still_failed = []

        for data in self.download_state.failed_downloads:
            failed_download_info = DownloadInfo(
                item_url=data["item_url"],
                download_link=data["download_link"],
                filename=data["filename"],
                task=data["id"],
                item_date=data.get("item_date"),
            )
            failed_again = await self._retry_failed_download(failed_download_info)
            if failed_again:
                still_failed.append(data)

            # Update the persisted state with the outcome of this final pass.
            await self._persist_item_state(
                data["item_url"], data["filename"], failed=failed_again,
            )

        self.download_state.failed_downloads.clear()
        return still_failed
