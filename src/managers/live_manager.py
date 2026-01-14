"""Module that provides functionality for managing and displaying live updates.

It combines a progress table and a logger table into a real-time display, allowing
dynamic updates of both tables. The `LiveManager` class handles the integration and
refresh of the live view.
"""

from __future__ import annotations

import datetime
import importlib
import time
from contextlib import nullcontext
from typing import TYPE_CHECKING

from rich.console import Group
from rich.live import Live

from src.config import (
    CompletedReason,
    FailedReason,
    SkippedReason,
    TaskResult,
    TASK_REASON_MAPPING,
)
from src.file_utils import get_session_entries_count, write_verbose_log

from .log_manager import LoggerTable
from .progress_manager import ProgressManager

if TYPE_CHECKING:
    from enum import IntEnum


class LiveManager:  # pylint: disable=R0902,R0913
    """Manage a live display that combines a progress table and a logger table.

    It allows for real-time updates and refreshes of both progress and logs in a
    terminal.
    """

    def __init__(
        self,
        progress_manager: ProgressManager,
        logger_table: LoggerTable,
        *,
        disable_ui: bool = False,
        refresh_per_second: int = 10,
        verbose: bool = False,
    ) -> None:
        """Initialize the progress manager and logger, and set up the live view."""
        self.progress_manager = progress_manager
        self.logger_table = logger_table
        self.disable_ui = disable_ui
        self.verbose = verbose

        # Track last announced paths so we can refresh the header if they change
        self._last_session_path: str | None = None
        self._last_verbose_path: str | None = None

        if self.verbose:
            cfg = importlib.import_module("src.config")
            session_path = getattr(cfg, "SESSION_LOG", "")
            verbose_path = getattr(cfg, "VERBOSE_LOG", "")
            write_verbose_log(f"Session log: {session_path}")
            write_verbose_log(f"Verbose log: {verbose_path}")
            header = f"Session: {session_path} | Verbose: {verbose_path}"

            try:
                self.logger_table.set_header_subtitle(header)

            except Exception:
                self.logger_table.log("Logs", header)

            self.logger_table.log("Logs", header)
            self._last_session_path = session_path
            self._last_verbose_path = verbose_path

        self.progress_table = self.progress_manager.create_progress_table()

        # Set up the live display (rendering uses the created progress table)
        self.live = (
            Live(self._render_live_view(), refresh_per_second=refresh_per_second)
            if not self.disable_ui
            else nullcontext()
        )

        self.start_time = time.time()
        self.update_log(
            event="Script started",
            details="The script has started execution.",
        )

    def add_overall_task(self, description: str, num_tasks: int) -> None:
        """Call ProgressManager to add an overall task."""
        self.progress_manager.add_overall_task(description, num_tasks)

    def increment_post_retry_count(self, amount: int = 1) -> None:
        """Increment the shared post-task retry counter."""
        try:
            self.progress_manager.increment_post_retry_count(amount)

        except Exception:
            pass

    def reset_post_retry_count(self) -> None:
        """Reset the shared post-task retry counter to zero."""
        try:
            self.progress_manager.reset_post_retry_count()

        except Exception:
            pass

    def set_post_retry_count(self, value: int) -> None:
        """Set the shared post-task retry counter to a specific value."""
        try:
            self.progress_manager.set_post_retry_count(value)

        except Exception:
            pass

    def add_task(
        self, current_task: int = 0, total: int = 100, base_one: bool = False,
    ) -> None:
        """Call ProgressManager to add an individual task.

        The `base_one` flag indicates whether `current_task` should be treated
        as a 1-based index for display purposes.
        """
        return self.progress_manager.add_task(current_task, total, base_one=base_one)

    def update_task(
        self,
        task_id: int,
        completed: int | None = None,
        advance: int = 0,
        *,
        visible: bool = True,
    ) -> None:
        """Call ProgressManager to update an individual task."""
        self.progress_manager.update_task(task_id, completed, advance, visible=visible)

    def update_log(self, *, event: str, details: str) -> None:
        """Log an event and refreshes the live display."""
        if self.verbose:
            try:
                cfg = importlib.import_module("src.config")
                session_path = getattr(cfg, "SESSION_LOG", "")
                verbose_path = getattr(cfg, "VERBOSE_LOG", "")

                if (
                    session_path != self._last_session_path
                    or verbose_path != self._last_verbose_path
                ):
                    write_verbose_log(f"Session log: {session_path}")
                    write_verbose_log(f"Verbose log: {verbose_path}")
                    header = f"Session: {session_path} | Verbose: {verbose_path}"

                    try:
                        self.logger_table.set_header_subtitle(header)

                    except Exception:
                        self.logger_table.log("Logs", header)

                    self.logger_table.log("Logs", header)
                    self._last_session_path = session_path
                    self._last_verbose_path = verbose_path

            except Exception:
                pass

        self.logger_table.log(event, details, disable_ui=self.disable_ui)
        if self.verbose:
            if not self.disable_ui:
                timestamp = time.strftime("%H:%M:%S")
                write_verbose_log(f"[{timestamp}] Event: {event} | Details: {details}")

        if not self.disable_ui:
            self.live.update(self._render_live_view())

    def start(self) -> None:
        """Start the live display."""
        if not self.disable_ui:
            self.live.start()

    def stop(self) -> None:
        """Stop the live display, log the execution time and a summary of results."""
        execution_time = self._compute_execution_time()

        # Log the execution time in hh:mm:ss format, and file download statistics
        self.update_log(
            event="Script ended",
            details="The script has finished execution.\n"
            f"Execution time: {execution_time}",
        )

        # Log a summary of task execution results
        self._log_detailed_results_summary()

        if not self.disable_ui:
            self.live.stop()

        # After stopping the live view, output a final summary for both UI and
        # headless runs (this will print to console when UI disabled and also
        # write to the verbose log when enabled).
        try:
            self.final_summary()

        except Exception:
            pass

    def final_summary(self) -> None:
        """Compose and output a final summary of the run.

        The summary includes total tasks, completed tasks, and number of
        session-file entries (deferred URLs). For headless runs the summary is
        printed to stdout; for UI runs it is appended to the logger table and
        verbose log if enabled.
        """
        try:
            total = self.progress_manager.get_total_tasks()
            completed = self.progress_manager.get_completed_tasks()
            deferred_count, session_path = (0, "")
            try:
                deferred_count, session_path = get_session_entries_count()

            except Exception:
                pass

            summary = (
                f"Run summary: completed {completed}/{total} | "
                f"deferred: {deferred_count} | session: {session_path}"
            )

            # Log into the logger table
            try:
                self.logger_table.log("Summary", summary, disable_ui=self.disable_ui)

            except Exception:
                pass

            # Also write to verbose log if enabled
            if self.verbose:
                try:
                    write_verbose_log(summary)

                except Exception:
                    pass

            # For headless runs, print a compact line to stdout so users see it
            if self.disable_ui:
                try:
                    print(summary, flush=True)

                except Exception:
                    pass

        except Exception:
            pass

    # Private methods
    def _render_live_view(self) -> Group:
        """Render the combined live view of the progress table and the logger table."""
        # Rebuild the progress table each render so dynamic subtitles (like
        # the post-task retry count) are always up-to-date.
        panel_width = self.progress_manager.get_panel_width()
        self.progress_table = self.progress_manager.create_progress_table()
        return Group(
            self.progress_table,
            self.logger_table.render_log_panel(panel_width=2 * panel_width),
        )

    def _compute_execution_time(self) -> str:
        """Compute and format the execution time of the script."""
        execution_time = time.time() - self.start_time
        time_delta = datetime.timedelta(seconds=execution_time)

        # Extract hours, minutes, and seconds from the timedelta object
        hours = time_delta.seconds // 3600
        minutes = (time_delta.seconds % 3600) // 60
        seconds = time_delta.seconds % 60

        return f"{hours:02} hrs {minutes:02} mins {seconds:02} secs"

    def _log_results_summary(self) -> None:
        max_stat_len = max(len(result.name) for result in TaskResult)
        details = "\n".join(
            f"{result.name.capitalize():<{max_stat_len}}: "
            f"{self.progress_manager.get_result_count(result)}"
            for result in TaskResult
        )
        self.update_log(event="Results summary", details=details)

    def _log_detailed_results_summary(self) -> None:
        """Log task results with the corresponding task reason.

        Avoid printing task reasons having one enum member only and task reasons with
        zero records.
        """
        max_stat_len = max(len(result.name) for result in TaskResult)
        details = []

        def log_reason(result: TaskResult, reason_class: type[IntEnum]) -> None:
            for reason in reason_class:
                count = self.progress_manager.get_result_count(result, reason)
                if count > 0:
                    reason_name = reason.name.replace("_", " ").capitalize()
                    formatted_reason = f"- {reason_name}: {count}"
                    details.append(formatted_reason)

        for result in TaskResult:
            result_count = self.progress_manager.get_result_count(result)
            result_name = result.name.capitalize()
            details.append(f"{result_name:<{max_stat_len}}: {result_count}")

            if result in TASK_REASON_MAPPING:
                reason_class = TASK_REASON_MAPPING[result]
                if len(reason_class) > 1:
                    log_reason(result, reason_class)

        self.update_log(event="Results summary", details="\n".join(details))


def initialize_managers(
    *, disable_ui: bool = False, verbose: bool = False,
) -> LiveManager:
    """Initialize and return the managers for progress tracking and logging.

    The `verbose` flag is forwarded to the logger so logs can be duplicated to file.
    """
    progress_manager = ProgressManager(task_name="Album", item_description="File")
    logger_table = LoggerTable(verbose=verbose)
    return LiveManager(
        progress_manager,
        logger_table,
        disable_ui=disable_ui,
        verbose=verbose,
    )
