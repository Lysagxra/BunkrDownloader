"""Module that provides tools to manage the downloading of individual files from Bunkr.

It supports retry mechanisms, progress tracking, and error handling for a robust
download experience.
"""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import TYPE_CHECKING

import requests
from requests import RequestException

from helpers.bunkr_utils import mark_subdomain_as_offline, subdomain_is_offline
from helpers.config import (
    DOWNLOAD_HEADERS,
    DownloadInfo,
    HTTPStatus,
    SessionInfo,
)
from helpers.file_utils import write_on_session_log
from helpers.general_utils import truncate_filename

from .download_utils import save_file_with_progress

if TYPE_CHECKING:
    from helpers.managers.live_manager import LiveManager


class MediaDownloader:
    """Manage the downloading of individual files from Bunkr URLs."""

    def __init__(
        self,
        session_info: SessionInfo,
        download_info: DownloadInfo,
        live_manager: LiveManager,
        retries: int = 5,
    ) -> None:
        """Initialize the MediaDownloader instance."""
        self.session_info = session_info
        self.download_info = download_info
        self.live_manager = live_manager
        self.retries = retries

    def attempt_download(self, final_path: str) -> bool:
        """Attempt to download the file with retries."""
        for attempt in range(self.retries):
            try:
                response = requests.get(
                    self.download_info.download_link,
                    stream=True,
                    headers=DOWNLOAD_HEADERS,
                    timeout=30,
                )
                response.raise_for_status()

            except RequestException as req_err:
                # Exit the loop if not retrying
                if not self._handle_request_exception(req_err, attempt):
                    break

            else:
                # Returns True if the download failed (marked as partial), otherwise
                # False to indicate a successful download and exit the loop.
                return save_file_with_progress(
                    response,
                    final_path,
                    self.download_info.task,
                    self.live_manager,
                )

        # Download failed
        return True

    def download(self) -> dict | None:
        """Handle the download process."""
        is_final_attempt = self.retries == 1
        is_offline = subdomain_is_offline(
            self.download_info.download_link,
            self.session_info.bunkr_status,
        )

        if is_offline and is_final_attempt:
            self.live_manager.update_log(
                "Non-operational subdomain",
                f"The subdomain for {self.download_info.filename} could be offline. "
                "Check the log file.",
            )
            write_on_session_log(self.download_info.download_link)
            self.live_manager.update_task(self.download_info.task, visible=False)
            return None

        formatted_filename = truncate_filename(self.download_info.filename)
        final_path = Path(self.session_info.download_path) / formatted_filename

        # Skip download if the file exists or is blacklisted
        if self._skip_file_download(final_path):
            return None

        # Attempt to download the file with retries
        failed_download = self.attempt_download(final_path)

        # Handle failed download after retries
        if failed_download:
            return self._handle_failed_download(is_final_attempt=is_final_attempt)

        return None

    # Private methods
    def _skip_file_download(self, final_path: str) -> bool:
        """Determine whether a file should be skipped during download.

        This method checks the following conditions:
        - If the file already exists at the specified path.
        - If the file's name matches any pattern in the ignore list.
        - If the file's name does not match any pattern in the include list.

        If any of these conditions are met, the download is skipped, and appropriate
        logs are updated.
        """
        ignore_list = getattr(self.session_info.args, "ignore", [])
        include_list = getattr(self.session_info.args, "include", [])

        def log_and_skip_event(reason: str) -> bool:
            """Log the skip reason and updates the task before."""
            self.live_manager.update_log("Skipped download", reason)
            self.live_manager.update_task(
                self.download_info.task,
                completed=100,
                visible=False,
            )
            return True

        # Check if the file already exists
        if Path(final_path).exists():
            return log_and_skip_event(
                f"{self.download_info.filename} has already been downloaded.",
            )

        # Check if the file is in the ignore list
        if ignore_list and any(
            word in self.download_info.filename for word in ignore_list
        ):
            return log_and_skip_event(
                f"{self.download_info.filename} matches the ignore list.",
            )

        # Check if the file is not in the include list
        if include_list and all(
            word not in self.download_info.filename for word in include_list
        ):
            return log_and_skip_event(
                f"No included words found for {self.download_info.filename}.",
            )

        # If none of the skip conditions are met, do not skip
        return False

    def _retry_with_backoff(self, attempt: int, *, event: str) -> bool:
        """Log error, apply backoff, and return True if should retry."""
        self.live_manager.update_log(
            event,
            f"{event} for {self.download_info.filename} ({attempt + 1}/{self.retries})",
        )

        if attempt < self.retries - 1:
            delay = 3 ** (attempt + 1) + random.uniform(1, 3)  # noqa: S311
            time.sleep(delay)
            return True

        return False

    def _handle_request_exception(
        self, req_err: RequestException, attempt: int,
    ) -> bool:
        """Handle exceptions during the request and manages retries."""
        is_server_down = (
            req_err.response is None
            or req_err.response.status_code == HTTPStatus.SERVER_DOWN
        )

        # Mark the subdomain as offline and exit the loop
        if is_server_down:
            marked_subdomain = mark_subdomain_as_offline(
                self.session_info.bunkr_status,
                self.download_info.download_link,
            )
            self.live_manager.update_log(
                "No response",
                f"Subdomain {marked_subdomain} has been marked as offline.",
            )
            return False

        if req_err.response.status_code in (
            HTTPStatus.TOO_MANY_REQUESTS,
            HTTPStatus.SERVICE_UNAVAILABLE,
        ):
            return self._retry_with_backoff(attempt, event="Too many requests")

        if req_err.response.status_code == HTTPStatus.BAD_GATEWAY:
            self.live_manager.update_log(
                "Server error",
                f"Bad gateway for {self.download_info.filename}.",
            )
            # Setting retries to 1 forces an immediate failure on the next check.
            self.retries = 1
            return False

        # Do not retry, exit the loop
        self.live_manager.update_log("Request error", str(req_err))
        return False

    def _handle_failed_download(self, *, is_final_attempt: bool) -> dict | None:
        """Handle a failed download after all retry attempts."""
        if not is_final_attempt:
            self.live_manager.update_log(
                "Exceeded retry attempts",
                f"Exceeded retry attempts for {self.download_info.filename}. "
                "It will be retried one more time after all other tasks.",
            )
            return {
                "id": self.download_info.task,
                "filename": self.download_info.filename,
                "download_link": self.download_info.download_link,
            }

        self.live_manager.update_log(
            "Download failed",
            f"Failed to download {self.download_info.filename}. Check the log file.",
        )
        self.live_manager.update_task(self.download_info.task, visible=False)
        return None
