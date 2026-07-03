"""Module that facilitates the downloading of entire Bunkr albums.

This module provides features for managing progress, handling failed downloads, and
integrating with live task displays.
"""

import asyncio
from asyncio import Semaphore
from pathlib import Path

from src.config import MAX_RETRIES, MAX_WORKERS, AlbumInfo, DownloadInfo, FailedReason, SessionInfo, SkippedReason
from src.crawlers.crawler_utils import get_download_info
from src.file_utils import truncate_filename
from src.general_utils import fetch_page
from src.managers.live_manager import LiveManager
from src.managers.state_manager import save_album_state

from .media_downloader import MediaDownloader


class AlbumDownloader:
    """Manage the downloading of entire Bunkr albums."""

    def __init__(
        self,
        session_info: SessionInfo,
        album_info: AlbumInfo,
        live_manager: LiveManager,
        cached_items: dict[str, dict] | None = None,
    ) -> None:
        """Initialize the AlbumDownloader instance.

        Args:
            cached_items: Per-item state persisted from a previous run for
                this same album (keyed by item page URL), used to skip
                already-completed items without any network round-trip.
        """
        self.session_info = session_info
        self.album_info = album_info
        self.live_manager = live_manager
        self.failed_downloads = []
        self.unresolved_failures = 0
        self.cached_items = dict(cached_items or {})
        self._state_lock = asyncio.Lock()

    async def execute_item_download(
        self,
        item_page: str,
        current_task: int,
        semaphore: Semaphore,
        max_retries: int,
    ) -> None:
        """Handle the download of an individual item in the album."""
        async with semaphore:
            # Fast path: this item was confirmed downloaded on a previous
            # run and the file is still on disk — skip entirely without
            # fetching the item page or calling the signing API.
            cached = self.cached_items.get(item_page)
            if cached and cached.get("status") == "completed":
                cached_filename = cached.get("filename", "")
                expected_path = (
                    Path(self.session_info.download_path)
                    / truncate_filename(cached_filename)
                )
                if expected_path.exists():
                    task = self.live_manager.add_task(current_task=current_task)
                    self.live_manager.update_log(
                        event="Skipped download",
                        details=f"{cached_filename} has already been downloaded "
                        "(cached from a previous run).",
                    )
                    self.live_manager.update_task(task, completed=100, visible=False)
                    self.live_manager.update_summary(SkippedReason.ALREADY_DOWNLOADED)
                    return
                # The cached file is missing (user deleted it, or the state
                # was stale) — fall through and process normally below.

            task = self.live_manager.add_task(current_task=current_task)

            # Process the download of an item
            item_soup = await self._fetch_page_with_retries(item_page)
            item_download_link, item_filename = await get_download_info(
                item_page,
                item_soup,
            )

            # Download item
            if item_download_link:
                media_downloader = MediaDownloader(
                    session_info=self.session_info,
                    download_info=DownloadInfo(
                        item_url=item_page,
                        download_link=item_download_link,
                        filename=item_filename,
                        task=task,
                    ),
                    live_manager=self.live_manager,
                    retries=max_retries,
                    has_external_retry=True,
                )

                failed_download = await asyncio.to_thread(media_downloader.download)
                if failed_download:
                    self.failed_downloads.append({
                        "id": task,
                        "filename": item_filename,
                        "download_link": item_download_link,
                        "item_url": item_page,
                    })

                await self._persist_item_state(
                    item_page, item_filename, failed=failed_download,
                )

            else:
                # URL could not be resolved after all retries — report as failed
                # so the user knows which files need attention. There is no
                # download_link to retry with, so this counts as permanent.
                self.live_manager.update_log(
                    event="Download failed",
                    details=f"Could not resolve a download URL for {item_filename}.",
                )
                self.live_manager.update_task(task, completed=100, visible=False)
                self.live_manager.update_summary(FailedReason.MAX_RETRIES_REACHED)
                self.unresolved_failures += 1
                await self._persist_item_state(item_page, item_filename, failed=True)

    async def download_album(
        self,
        max_workers: int = MAX_WORKERS,
        max_retries: int = MAX_RETRIES,
    ) -> bool:
        """Handle the album download.

        Returns:
            True if the album ended with at least one permanently failed
            item (after the extra retry pass), False if every item either
            succeeded or was intentionally skipped.
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
            await self._process_failed_downloads() if self.failed_downloads else []
        )
        return bool(still_failed) or self.unresolved_failures > 0

    # Private methods
    async def _persist_item_state(
        self, item_page: str, filename: str, *, failed: bool,
    ) -> None:
        """Record this item's outcome and persist the album state to disk.

        Marks the item "completed" only when the download did not fail AND
        the file is verifiably present on disk — this stays accurate
        regardless of *why* the download call returned success (a fresh
        download, an already-existed skip, or an offline-domain skip all
        funnel through here).
        """
        is_completed = False
        if not failed:
            expected_path = (
                Path(self.session_info.download_path) / truncate_filename(filename)
            )
            is_completed = expected_path.exists()

        async with self._state_lock:
            self.cached_items[item_page] = {
                "filename": filename,
                "status": "completed" if is_completed else "failed",
            }
            save_album_state(
                self.session_info.download_path,
                self.album_info.album_id,
                self.album_info.item_pages,
                self.cached_items,
            )

    async def _fetch_page_with_retries(
        self,
        item_page: str,
        max_retries: int = MAX_RETRIES,
        base_delay: float = 1.5,
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
            retries=1,  # Retry once for failed downloads
            has_external_retry=False,  # this is the last chance, finalize either way
        )
        # Run the synchronous download function in a separate thread
        return await asyncio.to_thread(media_downloader.download)

    async def _process_failed_downloads(self) -> list[dict]:
        """Retry every failed download once more.

        Returns:
            The subset of failed_downloads that failed again on this retry
            pass (i.e. permanently failed).
        """
        still_failed = []
        for data in self.failed_downloads:
            failed_download_info = DownloadInfo(
                item_url=data["item_url"],
                download_link=data["download_link"],
                filename=data["filename"],
                task=data["id"],
            )
            failed_again = await self._retry_failed_download(failed_download_info)
            if failed_again:
                still_failed.append(data)

            # Update the persisted state with the outcome of this final pass.
            await self._persist_item_state(
                data["item_url"], data["filename"], failed=failed_again,
            )

        self.failed_downloads.clear()
        return still_failed
