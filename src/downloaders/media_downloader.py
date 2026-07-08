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

from src.bunkr_utils import mark_subdomain_as_offline, subdomain_is_offline
from src.config import (
    DOWNLOAD_HEADERS,
    CompletedReason,
    DownloadConfig,
    DownloadInfo,
    FailedReason,
    HTTPStatus,
    RetryConfig,
    SessionInfo,
    SkippedReason,
)
from src.file_utils import (
    matches_ignore_list,
    matches_include_list,
    truncate_filename,
    write_on_session_log,
)

from .download_utils import (
    detect_range_support,
    save_file_with_chunks,
    save_file_with_progress,
    should_use_parallel_download,
)

if TYPE_CHECKING:
    from src.managers.live_manager import LiveManager


class MediaDownloader:
    """Manage the downloading of individual files from Bunkr URLs."""

    def __init__(
        self,
        session_info: SessionInfo,
        download_info: DownloadInfo,
        live_manager: LiveManager,
        retry_config: RetryConfig,
    ) -> None:
        """Initialize the MediaDownloader instance."""
        self.session_info = session_info
        self.download_info = download_info
        self.live_manager = live_manager
        self.retry_config = retry_config

    def attempt_download(self, final_path: str) -> bool:
        """Attempt to download the file, using parallel chunks when possible.

        If the server supports byte-range requests and the file is large enough,
        the download is split into num_connections parallel chunks (each saved
        as a .partN file to allow resuming).  Falls back to the original
        single-connection stream when chunking is not applicable.

        The chunked path honors the same outer retry budget (--max-retries)
        as the single-connection fallback: a persistent failure (all internal
        per-chunk retries exhausted) triggers the same exponential back-off
        and re-attempt cycle via _retry_with_backoff, instead of giving up
        after a single call.

        Returns True if the download failed, False on success.
        """
        num_connections = getattr(self.session_info.args, "connections", 1)
        rate_limiter = self.session_info.rate_limiter

        for attempt in range(self.retry_config.retries):
            try:
                supports_range, content_length = detect_range_support(
                    self.download_info.download_link, DOWNLOAD_HEADERS,
                )

                if should_use_parallel_download(
                    content_length, num_connections, supports_range=supports_range,
                ):
                    # .partN files are preserved on failure so a re-attempt
                    # (here or on a future run) resumes instead of restarting.
                    chunked_failed = save_file_with_chunks(
                        self.download_info.download_link,
                        final_path,
                        self.download_info.task,
                        self.live_manager,
                        DownloadConfig(
                            content_length=content_length,
                            num_connections=num_connections,
                            headers=DOWNLOAD_HEADERS,
                            rate_limiter=rate_limiter,
                        ),
                    )
                    if not chunked_failed:
                        return False

                    # Persistent failure after CHUNK_MAX_RETRIES internal
                    # attempts -- consume one outer retry slot, same as a
                    # request-level failure on the fallback path below.
                    if not self._retry_with_backoff(
                        attempt, event="Retrying chunked download",
                    ):
                        break

                    continue

                # Fallback: single-connection streaming download
                response = requests.get(
                    self.download_info.download_link,
                    stream=True,
                    headers=DOWNLOAD_HEADERS,
                    timeout=30,
                )
                response.raise_for_status()

            except RequestException as req_err:
                if not self._handle_request_exception(req_err, attempt):
                    break

            else:
                return save_file_with_progress(
                    response,
                    final_path,
                    self.download_info.task,
                    self.live_manager,
                    rate_limiter=rate_limiter,
                )

        return True

    def download(self) -> bool:
        """Handle the download process.

        Returns:
            True if the item ultimately failed (and no one else will retry it),
            False if it succeeded, was skipped, or will be retried later by an external
            caller (has_external_retry=True).

        """
        is_final_attempt = not self.retry_config.has_external_retry
        is_offline = subdomain_is_offline(
            self.download_info.download_link,
            self.session_info.bunkr_status,
        )

        if is_offline and is_final_attempt:
            self.live_manager.update_log(
                event="Non-operational subdomain",
                details=f"The subdomain for {self.download_info.filename} is offline. "
                "Check the log file.",
            )
            self._finalize_download(SkippedReason.DOMAIN_OFFLINE)
            return False

        formatted_filename = truncate_filename(self.download_info.filename)
        final_path = Path(self.session_info.download_path) / formatted_filename

        # Skip download if the file exists or is blacklisted
        if self._skip_file_download(final_path):
            return False

        # Attempt to download the file with retries
        try:
            failed_download = self.attempt_download(final_path)

        except requests.exceptions.ConnectionError:
            self.live_manager.update_log(
                event="Connection error",
                details=f"Read timed out for {self.download_info.filename}",
            )
            failed_download = True

        # Handle failed download after retries
        if failed_download:
            return self._handle_failed_download(is_final_attempt=is_final_attempt)

        self.live_manager.update_summary(CompletedReason.DOWNLOAD_SUCCESS)
        return False

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
            self.live_manager.update_log(event="Skipped download", details=reason)
            self.live_manager.update_task(
                self.download_info.task,
                completed=100,
                visible=False,
            )
            return True

        # Check if the file already exists
        if Path(final_path).exists():
            self.live_manager.update_summary(SkippedReason.ALREADY_DOWNLOADED)
            return log_and_skip_event(
                f"{self.download_info.filename} has already been downloaded.",
            )

        # Check if the file is in the ignore list
        if matches_ignore_list(self.download_info.filename, ignore_list):
            self.live_manager.update_summary(SkippedReason.IGNORE_LIST)
            return log_and_skip_event(
                f"{self.download_info.filename} matches the ignore list.",
            )

        # Check if the file is not in the include list
        if matches_include_list(self.download_info.filename, include_list):
            self.live_manager.update_summary(SkippedReason.INCLUDE_LIST)
            return log_and_skip_event(
                f"No included words found for {self.download_info.filename}.",
            )

        # Check if the subdomain is marked as offline
        if subdomain_is_offline(
            self.download_info.download_link, self.session_info.bunkr_status,
        ):
            self._finalize_download(SkippedReason.DOMAIN_OFFLINE)
            return log_and_skip_event(
                f"The subdomain for {self.download_info.download_link} has been "
                "previously marked as offline.",
            )

        # If none of the skip conditions are met, do not skip
        return False

    def _retry_with_backoff(self, attempt: int, *, event: str) -> bool:
        """Log error, apply backoff, and return True if should retry."""
        self.live_manager.update_log(
            event=event,
            details=f"{event} for {self.download_info.filename} "
            f"({attempt + 1}/{self.retry_config.retries})...",
        )

        if attempt < self.retry_config.retries - 1:
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
            or req_err.response.status_code in (
                HTTPStatus.SERVER_DOWN,
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        )

        # Mark the subdomain as offline and exit the loop
        if is_server_down:
            marked_subdomain = mark_subdomain_as_offline(
                self.session_info.bunkr_status,
                self.download_info.download_link,
            )
            self.live_manager.update_log(
                event="No response",
                details=f"Subdomain '{marked_subdomain}' has been marked as offline.",
            )
            return False

        if req_err.response.status_code == HTTPStatus.TOO_MANY_REQUESTS:
            return self._retry_with_backoff(attempt, event="Retrying download")

        if req_err.response.status_code == HTTPStatus.BAD_GATEWAY:
            self.live_manager.update_log(
                event="Server error",
                details=f"Bad gateway for {self.download_info.filename}.",
            )
            # Setting retries to 1 forces an immediate failure on the next check.
            self.retry_config.retries = 1
            return False

        # Do not retry, exit the loop
        self.live_manager.update_log(event="Request error", details=str(req_err))
        return False

    def _handle_failed_download(self, *, is_final_attempt: bool) -> bool:
        """Handle a failed download after all retry attempts.

        Always returns True (failed). When this is not the final attempt,
        only a log line is emitted -- the caller (AlbumDownloader) already
        has everything it needs to retry the item itself and is expected
        to do so. The session log is only written on the final attempt,
        since that is the only point at which the outcome is permanent.
        """
        if not is_final_attempt:
            self.live_manager.update_log(
                event="Exceeded retry attempts",
                details=f"Max retries reached for {self.download_info.filename}. "
                "It will be retried one more time after all other tasks.",
            )
            return True

        self.live_manager.update_log(
            event="Download failed",
            details=f"Failed to download {self.download_info.filename}. "
            "Check the log file.",
        )
        self._finalize_download(FailedReason.MAX_RETRIES_REACHED)
        return True

    def _finalize_download(
        self,
        reason: FailedReason | SkippedReason,
        *,
        completed: int | None = None,
    ) -> None:
        outcome = reason.__class__.__name__.replace("Reason", "")

        write_on_session_log(
            self.download_info,
            reason=reason,
            outcome=outcome,
        )

        self.live_manager.update_task(
            self.download_info.task,
            completed=completed,
            visible=False,
        )
        self.live_manager.update_summary(reason)
