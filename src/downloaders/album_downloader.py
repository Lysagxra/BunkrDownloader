"""Module that facilitates the downloading of entire Bunkr albums.

This module provides features for managing progress, handling failed downloads, and
integrating with live task displays.
"""

import asyncio
from asyncio import Semaphore

from src.config import MAX_WORKERS, AlbumInfo, DownloadInfo, SessionInfo
from src.crawlers.crawler_utils import get_download_info
from src.general_utils import fetch_page
from src.managers.live_manager import LiveManager

from .media_downloader import MediaDownloader


class AlbumDownloader:
    """Manage the downloading of entire Bunkr albums."""

    def __init__(
        self,
        session_info: SessionInfo,
        album_info: AlbumInfo,
        live_manager: LiveManager,
    ) -> None:
        """Initialize the AlbumDownloader instance."""
        self.session_info = session_info
        self.album_info = album_info
        self.live_manager = live_manager
        self.failed_downloads = []

    async def execute_item_download(
        self,
        item_page: str,
        current_task: int,
        semaphore: Semaphore,
    ) -> None:
        """Handle the download of an individual item in the album."""
        async with semaphore:
            task = self.live_manager.add_task(current_task=current_task)

            # Process the download of an item
            item_soup = await fetch_page(item_page)
            if item_soup is None:
                # Could not fetch page; log and hide task early.
                try:
                    self.live_manager.update_log(
                        event="Fetch failed",
                        details=f"Failed to fetch item page {item_page} (task {current_task + 1}).",
                    )
                except Exception:
                    pass
                try:
                    self.live_manager.update_task(task, completed=100, visible=False)
                except Exception:
                    pass
                return

            item_download_link, item_filename = await get_download_info(
                item_page, item_soup,
            )

            # Download item
            if item_download_link:
                # Compute a 1-based display index once and reuse it so other
                # components can reference the same human-facing index.
                display_index = current_task + 1
                media_downloader = MediaDownloader(
                    session_info=self.session_info,
                    download_info=DownloadInfo(
                        download_link=item_download_link,
                        filename=item_filename,
                        task=task,
                        display_index=display_index,
                    ),
                    live_manager=self.live_manager,
                    retries=getattr(self.session_info.args, "retries", 5),
                )

                failed_download = await asyncio.to_thread(media_downloader.download)
                if failed_download:
                    # Ensure failed_download includes display_index if available.
                    # Prefer the value from the MediaDownloader's DownloadInfo
                    # (it should have been set during initialization).
                    if "display_index" not in failed_download:
                        try:
                            failed_download["display_index"] = (
                                media_downloader.download_info.display_index
                            )
                        except Exception:
                            failed_download["display_index"] = display_index
                    self.failed_downloads.append(failed_download)

    async def download_album(self, max_workers: int = MAX_WORKERS) -> None:
        """Handle the album download."""
        num_tasks = len(self.album_info.item_pages)
        self.live_manager.add_overall_task(
            description=self.album_info.album_id,
            num_tasks=num_tasks,
        )

        # Create tasks for downloading each item in the album
        semaphore = asyncio.Semaphore(max_workers)
        tasks = [
            self.execute_item_download(item_page, current_task, semaphore)
            for current_task, item_page in enumerate(self.album_info.item_pages)
        ]
        await asyncio.gather(*tasks)

        # If there are failed downloads, process them after all downloads are complete
        if self.failed_downloads:
            await self._process_failed_downloads()

    # Private methods
    async def _retry_failed_download(
        self,
        task: int,
        filename: str,
        download_link: str,
        display_index: int | None = None,
    ) -> None:
        """Handle failed downloads and retries them."""
        # Before retrying, re-show the task in the progress pane so users can
        # observe its progress during the retry pass.
        try:
            self.live_manager.update_task(task, visible=True)
        except Exception:
            # If the task can't be updated (UI disabled or removed), continue silently.
            pass

        media_downloader = MediaDownloader(
            session_info=self.session_info,
            download_info=DownloadInfo(download_link, filename, task, display_index=display_index),
            live_manager=self.live_manager,
            retries=1,  # Retry once for failed downloads
        )

        # Run the synchronous download function in a separate thread
        await asyncio.to_thread(media_downloader.download)

    async def _process_failed_downloads(self) -> None:
        """Process any failed downloads after the initial attempt."""
        for data in self.failed_downloads:
            await self._retry_failed_download(
                data["id"],
                data["filename"],
                data["download_link"],
                data.get("display_index"),
            )
        self.failed_downloads.clear()
