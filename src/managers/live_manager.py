"""Module that provides functionality for managing and displaying live updates.

It combines a progress table and a logger table into a real-time display, allowing
dynamic updates of both tables. The `LiveManager` class handles the integration and
refresh of the live view.
"""

from __future__ import annotations

import datetime
import time
from contextlib import nullcontext
from typing import TYPE_CHECKING

from rich.console import Group
from rich.live import Live

from src.config import REFRESH_PER_SECOND, TASK_REASON_MAPPING, TaskResult

from .log_manager import LoggerTable
from .progress_manager import ProgressManager
from .summary_manager import SummaryManager

if TYPE_CHECKING:
    from enum import IntEnum


class LiveManager:
    """Manage a live display that combines a progress table and a logger table.

    It allows for real-time updates and refreshes of both progress and logs in a
    terminal.
    """

    def __init__(
        self,
        progress_manager: ProgressManager,
        logger_table: LoggerTable,
        summary_manager: SummaryManager,
        *,
        disable_ui: bool = False,
    ) -> None:
        """Initialize the progress manager and logger, and set up the live view."""
        self.progress_manager = progress_manager
        self.progress_table = self.progress_manager.create_progress_table()
        self.logger_table = logger_table
        self.summary_manager = summary_manager
        self.disable_ui = disable_ui
        self.live = (
            Live(self._render_live_view(), refresh_per_second=REFRESH_PER_SECOND)
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

    def update_log(self, *, event: str, details: str) -> None:
        """Log an event and refreshes the live display."""
        self.logger_table.log(event, details, disable_ui=self.disable_ui)
        if not self.disable_ui:
            self.live.update(self._render_live_view())

    def update_summary(self, task_reason: IntEnum) -> None:
        """Update the task summary based on the given reason."""
        self.summary_manager.update_result(task_reason)

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
        """Log task results with the corresponding task reason.

        Avoid printing task reasons having one enum member only and task reasons with
        zero records.
        """
        max_stat_len = max(len(task_result.name) for task_result in TaskResult)
        details = []

        def log_reason(task_result: TaskResult, reason_class: type[IntEnum]) -> None:
            for reason in reason_class:
                num_results = self.summary_manager.get_result_count(task_result, reason)
                if num_results > 0:
                    reason_name = reason.name.replace("_", " ").capitalize()
                    formatted_reason = f"- {reason_name}: {num_results}"
                    details.append(formatted_reason)

        for task_result in TaskResult:
            num_results = self.summary_manager.get_result_count(task_result)
            result_name = task_result.name.capitalize()
            details.append(f"{result_name:<{max_stat_len}}: {num_results}")

            if task_result in TASK_REASON_MAPPING:
                reason_class = TASK_REASON_MAPPING[task_result]
                if len(reason_class) > 1:
                    log_reason(task_result, reason_class)

        self.update_log(event="Results summary", details="\n".join(details))


def initialize_managers(*, disable_ui: bool = False) -> LiveManager:
    """Initialize and return the managers for progress tracking and logging."""
    progress_manager = ProgressManager(task_name="Album", item_description="File")
    logger_table = LoggerTable()
    summary_manager = SummaryManager()
    return LiveManager(
        progress_manager,
        logger_table,
        summary_manager,
        disable_ui=disable_ui,
    )
