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
    MAX_RETRIES,
    CompletedReason,
    DownloadInfo,
    FailedReason,
    HTTPStatus,
    SessionInfo,
    SkippedReason,
)
from src.file_utils import (
    is_in_session_log,
    truncate_filename,
    write_on_session_log,
    write_verbose_log,
)
import traceback

from .download_utils import save_file_with_progress

if TYPE_CHECKING:
    from src.managers.live_manager import LiveManager


class MediaDownloader:
    """Manage the downloading of individual files from Bunkr URLs."""

    def __init__(
        self,
        session_info: SessionInfo,
        download_info: DownloadInfo,
        live_manager: LiveManager,
        retries: int = MAX_RETRIES,
    ) -> None:
        """Initialize the MediaDownloader instance."""
        self.session_info = session_info
        self.download_info = download_info
        self.live_manager = live_manager
        self.retries = retries
        # Display index is used in UI messages and is 1-based for humans.
        # Prefer the `display_index` stored on `DownloadInfo` so other
        # components can reuse the same value. If it's not set, compute it
        # from the task (1-based) and store it back on the DownloadInfo for
        # consistency.
        try:
            if getattr(self.download_info, "display_index", None) is None:
                # download_info.task should be an int, but guard defensively.
                self.download_info.display_index = int(self.download_info.task) + 1
            self.display_index = int(self.download_info.display_index)
        except Exception:
            # Fallback to a safe default for UI messages.
            self.display_index = 1

    def attempt_download(self, final_path: str) -> bool:
        """Attempt to download the file with retries, supporting resume via Range.

        Returns True if the download failed/partial, False on success.
        """
        final_path_obj = Path(final_path)
        temp_path = final_path_obj.with_suffix(".temp")

        for attempt in range(self.retries):
            # Prepare headers, optionally adding Range to resume
            headers = dict(DOWNLOAD_HEADERS)
            existing_temp_size = 0
            if temp_path.exists():
                try:
                    existing_temp_size = temp_path.stat().st_size
                except OSError:
                    existing_temp_size = 0

            if existing_temp_size > 0:
                headers["Range"] = f"bytes={existing_temp_size}-"
                try:
                    self.live_manager.update_log(
                        event="Resuming download",
                        details=(
                            f"Attempting to resume {self.download_info.filename} "
                                f"(#{self.display_index}) from byte {existing_temp_size}."
                        ),
                    )
                except Exception:
                    pass

            try:
                response = requests.get(
                    self.download_info.download_link,
                    stream=True,
                    headers=headers,
                    timeout=30,
                )
                response.raise_for_status()

            except RequestException as req_err:
                # Exit the loop if not retrying
                if not self._handle_request_exception(req_err, attempt):
                    break

            else:
                # If we requested a Range but server ignored it (200 OK), and we have
                # an existing temp file, remove it and retry once without Range.
                if existing_temp_size > 0 and response.status_code == 200:
                    # Server ignored Range request (returned 200). Remove temp and retry.
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass
                    try:
                        self.live_manager.update_log(
                            event="Range ignored",
                            details=(
                                    f"Server ignored Range for {self.download_info.filename} (#{self.display_index}); "
                                "removing partial and retrying from start."
                            ),
                        )
                    except Exception:
                        pass
                    headers.pop("Range", None)
                    try:
                        response = requests.get(
                            self.download_info.download_link,
                            stream=True,
                            headers=headers,
                            timeout=30,
                        )
                        response.raise_for_status()
                    except RequestException as req_err:
                        if not self._handle_request_exception(req_err, attempt):
                            break

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
        # If this download link is already present in the session log, skip it
        # for now — it will be retried during the post-task retry pass.
        # The retry manager can set `bypass_session_check` on the instance to
        # force a retry even if the URL is present in the session file.
        try:
            if not getattr(self, "bypass_session_check", False) and is_in_session_log(self.download_info.download_link):
                # Increment the counter first so the subsequent update_log call
                # will render the updated value immediately in the UI.
                try:
                    self.live_manager.increment_post_retry_count()
                except Exception:
                    pass

                # Log and hide the task from the album progress pane.
                try:
                    self.live_manager.update_log(
                        event="Deferred retry",
                        details=(
                            f"{self.download_info.filename} (#{self.display_index}) "
                            "is already listed in the session log and will be retried later."
                        ),
                    )
                except Exception:
                    pass
                try:
                    self.live_manager.update_task(self.download_info.task, visible=False)
                except Exception:
                    pass
                return None
        except Exception:
            # If anything goes wrong while checking the session log, continue
            # with the normal download flow.
            pass
        is_final_attempt = self.retries == 1
        is_offline = subdomain_is_offline(
            self.download_info.download_link,
            self.session_info.bunkr_status,
        )

        if is_offline and is_final_attempt:
            self.live_manager.update_log(
                event="Non-operational subdomain",
                details=(
                    f"The subdomain for {self.download_info.filename} (#{self.display_index}) is offline. "
                    "Check the log file."
                ),
            )
            write_verbose_log(f"caller: is_offline branch calling write_on_session_log for {self.download_info.download_link}")
            try:
                write_on_session_log(self.download_info.download_link)
                write_verbose_log(f"write_on_session_log succeeded (is_offline) for {self.download_info.download_link}")
            except Exception as ex:
                tb = traceback.format_exc()
                write_verbose_log(f"write_on_session_log raised (is_offline): {ex}\n{tb}")
            self.live_manager.update_task(self.download_info.task, visible=False)
            self.live_manager.update_summary(SkippedReason.DOMAIN_OFFLINE)
            return None

        formatted_filename = truncate_filename(self.download_info.filename)
        final_path = Path(self.session_info.download_path) / formatted_filename

        # Skip download if the file exists or is blacklisted
        if self._skip_file_download(final_path):
            return None

        # Attempt to download the file with retries
        try:
            failed_download = self.attempt_download(final_path)

        except requests.exceptions.ConnectionError:
            self.live_manager.update_log(
                event="Connection error",
                details="Read timed out for {self.download_info.filename}",
            )
            failed_download = True

        # Handle failed download after retries
        if failed_download:
            return self._handle_failed_download(is_final_attempt=is_final_attempt)
        # Successful download: mark task complete and hide it from the pane.
        try:
            self.live_manager.update_log(
                event="Download completed",
                details=f"{self.download_info.filename} (#{self.display_index}) downloaded successfully.",
            )
        except Exception:
            pass
        try:
            self.live_manager.update_task(
                self.download_info.task,
                completed=100,
                visible=False,
            )
        except Exception:
            pass

        self.live_manager.update_summary(CompletedReason.DOWNLOAD_SUCCESS)
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
                f"{self.download_info.filename} (#{self.display_index}) has already been downloaded.",
            )

        # Check if the file is in the ignore list
        if ignore_list and any(
            word in self.download_info.filename for word in ignore_list
        ):
            self.live_manager.update_summary(SkippedReason.IGNORE_LIST)
            return log_and_skip_event(
                f"{self.download_info.filename} (#{self.display_index}) matches the ignore list.",
            )

        # Check if the file is not in the include list
        if include_list and all(
            word not in self.download_info.filename for word in include_list
        ):
            self.live_manager.update_summary(SkippedReason.INCLUDE_LIST)
            return log_and_skip_event(
                f"No included words found for {self.download_info.filename} (#{self.display_index}).",
            )

        # Check if the subdomain is marked as offline
        if subdomain_is_offline(
            self.download_info.download_link, self.session_info.bunkr_status,
        ):
            write_on_session_log(self.download_info.download_link)
            self.live_manager.update_summary(SkippedReason.DOMAIN_OFFLINE)
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
            details=f"{event} for {self.download_info.filename} (#{self.display_index}) "
            f"({attempt + 1}/{self.retries})...",
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
                details=f"Bad gateway for {self.download_info.filename} (#{self.display_index}).",
            )
            # Setting retries to 1 forces an immediate failure on the next check.
            self.retries = 1
            return False

        # Do not retry, exit the loop
        self.live_manager.update_log(
            event="Request error",
            details=f"{req_err} (#{self.display_index})",
        )
        return False

    def _handle_failed_download(self, *, is_final_attempt: bool) -> dict | None:
        """Handle a failed download after all retry attempts."""
        if not is_final_attempt:
            # Increment the shared counter that tracks how many items will be
            # retried after the main download pass completes before logging so
            # the UI render shows the updated value immediately.
            try:
                self.live_manager.increment_post_retry_count()
            except Exception:
                pass
            # Also write the link to the session log now so the session file is
            # created and contains the link for later processing. This mirrors
            # previous behavior where final failures were written; doing it here
            # ensures the session file exists even before the retry pass.
            write_verbose_log(f"caller: exceeded-retry branch calling write_on_session_log for {self.download_info.download_link}")
            try:
                write_on_session_log(self.download_info.download_link)
                write_verbose_log(f"write_on_session_log succeeded (exceeded-retry) for {self.download_info.download_link}")
            except Exception as ex:
                tb = traceback.format_exc()
                write_verbose_log(f"write_on_session_log raised (exceeded-retry): {ex}\n{tb}")
            self.live_manager.update_log(
                event="Exceeded retry attempts",
                details=(
                        f"Max retries reached for {self.download_info.filename} (#{self.display_index}). "
                    "It will be retried one more time after all other tasks."
                ),
            )
            # Hide the task from the album progress pane until the retry pass.
            try:
                self.live_manager.update_task(self.download_info.task, visible=False)
            except Exception:
                # If the UI isn't available or the task is already removed, ignore.
                pass

            return {
                "id": self.download_info.task,
                "filename": self.download_info.filename,
                "download_link": self.download_info.download_link,
                "display_index": getattr(self.download_info, "display_index", None)
                    or self.display_index,
            }

        self.live_manager.update_log(
            event="Download failed",
            details=(
                f"Failed to download {self.download_info.filename} (#{self.display_index}). "
                "Check the log file."
            ),
        )
        # Write the failed download link to the session log so it can be retried later
        # (use the module-level import to avoid scoping issues)
        write_verbose_log(f"caller: final-failure branch calling write_on_session_log for {self.download_info.download_link}")
        try:
            write_on_session_log(self.download_info.download_link)
            write_verbose_log(f"write_on_session_log succeeded (final-failure) for {self.download_info.download_link}")
        except Exception as ex:
            tb = traceback.format_exc()
            write_verbose_log(f"write_on_session_log raised (final-failure): {ex}\n{tb}")

        # Ensure the task is hidden from the progress pane after final failure.
        try:
            self.live_manager.update_task(self.download_info.task, visible=False)
        except Exception:
            pass
        self.live_manager.update_task(self.download_info.task, visible=False)
        self.live_manager.update_summary(FailedReason.MAX_RETRIES_REACHED)
        return None
