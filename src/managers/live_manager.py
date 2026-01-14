"""Module that provides functionality for managing and displaying live updates.

It combines a progress table and a logger table into a real-time display, allowing
dynamic updates of both tables. The `LiveManager` class handles the integration and
refresh of the live view.
"""

from __future__ import annotations

import datetime
import time
from contextlib import nullcontext

from rich.console import Group
from rich.live import Live

from src.config import TaskResult

from .log_manager import LoggerTable
from .progress_manager import ProgressManager


class LiveManager:
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
    ) -> None:
        """Initialize the progress manager and logger, and set up the live view."""
        self.progress_manager = progress_manager
        self.progress_table = self.progress_manager.create_progress_table()
        self.logger_table = logger_table
        self.disable_ui = disable_ui
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

    def add_task(self, current_task: int = 0, total: int = 100) -> None:
        """Call ProgressManager to add an individual task."""
        return self.progress_manager.add_task(current_task, total)

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

    def update_result(self, task_result: TaskResult) -> None:
        """Update statistics of task results."""
        self.progress_manager.update_result(task_result)

    def update_log(self, *, event: str, details: str) -> None:
        """Log an event and refreshes the live display."""
        self.logger_table.log(event, details, disable_ui=self.disable_ui)
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
        self._log_results_summary()

        if not self.disable_ui:
            self.live.stop()

    # Private methods
    def _render_live_view(self) -> Group:
        """Render the combined live view of the progress table and the logger table."""
        panel_width = self.progress_manager.get_panel_width()
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


def initialize_managers(*, disable_ui: bool = False) -> LiveManager:
    """Initialize and return the managers for progress tracking and logging."""
    progress_manager = ProgressManager(task_name="Album", item_description="File")
    logger_table = LoggerTable()
    return LiveManager(progress_manager, logger_table, disable_ui=disable_ui)
