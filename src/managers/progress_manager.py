"""Provide a `ProgressManager` class for tracking and displaying the progress of tasks.

It uses the Rich library to create dynamic, formatted progress bars and tables for
monitoring task completion.
"""

from __future__ import annotations
from enum import Enum

import shutil

from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Column, Table

from src.config import (
    PROGRESS_COLUMNS_SEPARATOR,
    PROGRESS_MANAGER_COLORS,
    ProgressConfig,
)

class TaskResult(Enum):
    SUCCESS = 1
    FAILURE = 2
    SKIPPED = 3

class ProgressManager:
    """Manage and tracks the progress of multiple tasks.

    Displays individual progress bars for each task alongside an overall progress bar.
    """

    def __init__(
        self,
        task_name: str,
        item_description: str,
    ) -> None:
        """Initialize a progress tracking system for a specific task."""
        # Grouping progress-related configurations into a single object
        self.config = ProgressConfig(task_name, item_description)
        self.overall_progress = self._create_progress_bar()
        self.task_progress = self._create_progress_bar(show_time=True)
        self.num_tasks = 0
        self.num_success = 0
        self.num_failure = 0
        self.num_skipped = 0

    def get_panel_width(self) -> int:
        """Return the width of the panel."""
        return self.config.panel_width

    def add_overall_task(self, description: str, num_tasks: int) -> None:
        """Add an overall progress task with a given description and total tasks."""
        self.num_tasks = num_tasks
        overall_description = self._adjust_description(description)
        self.overall_progress.add_task(
            f"[{self.config.color}]{overall_description}",
            total=num_tasks,
            completed=0,
        )

    def add_task(self, current_task: int = 0, total: int = 100) -> int:
        """Add an individual task to the task progress bar."""
        task_description = (
            f"[{self.config.color}]{self.config.item_description} "
            f"{current_task + 1}/{self.num_tasks}"
        )
        return self.task_progress.add_task(task_description, total=total)

    def update_task(
        self,
        task_id: int,
        completed: int | None = None,
        advance: int = 0,
        *,
        visible: bool = True,
    ) -> None:
        """Update the progress of an individual task and the overall progress."""
        self.task_progress.update(
            task_id,
            completed=completed if completed is not None else None,
            advance=advance if completed is None else None,
            visible=visible,
        )
        self._update_overall_task(task_id)

    def update_result(self, task_result: TaskResult) -> None:
        """Update statistics of task results."""
        self._add_task_result(task_result)

    def create_progress_table(self, min_panel_width: int = 30) -> Table:
        """Create a formatted progress table for tracking the download."""
        terminal_width, _ = shutil.get_terminal_size()
        panel_width = max(min_panel_width, terminal_width // 2)

        progress_table = Table.grid()
        progress_table.add_row(
            Panel.fit(
                self.overall_progress,
                title=f"[bold {self.config.color}]Overall Progress",
                border_style=PROGRESS_MANAGER_COLORS["overall_border_color"],
                padding=(1, 1),
                width=panel_width,
            ),
            Panel.fit(
                self.task_progress,
                title=f"[bold {self.config.color}]{self.config.task_name} Progress",
                border_style=PROGRESS_MANAGER_COLORS["task_border_color"],
                padding=(1, 1),
                width=panel_width,
            ),
        )
        return progress_table

    def get_success_count(self) -> int:
        """Retrieve the number of successfully downloaded tasks."""
        return self.num_success

    def get_failure_count(self) -> int:
        """Retrieve the number of tasks that failed to download."""
        return self.num_failure

    def get_skipped_count(self) -> int:
        """Retrieve the number of skipped tasks as the media file has already been downloaded earlier."""
        return self.num_skipped
        
    def get_total_count(self) -> int:
        """Retrieve the number of skipped tasks as the media file has already been downloaded earlier."""
        return self.num_tasks

    # Private methods
    def _update_overall_task(self, task_id: int) -> None:
        """Advance the overall progress bar and removes old tasks."""
        # Access the latest task dynamically
        current_overall_task = self.overall_progress.tasks[-1]

        # If the task is finished, remove it and update the overall progress
        if self.task_progress.tasks[task_id].finished:
            self.overall_progress.advance(current_overall_task.id)
            self.task_progress.update(task_id, visible=False)

        # Track completed overall tasks
        if current_overall_task.finished:
            self.config.overall_buffer.append(current_overall_task)

        # Cleanup completed overall tasks
        self._cleanup_completed_overall_tasks()

    def _cleanup_completed_overall_tasks(self) -> None:
        """Remove the oldest completed overall task from the buffer and progress bar."""
        if len(self.config.overall_buffer) == self.config.overall_buffer.maxlen:
            completed_overall_id = self.config.overall_buffer.popleft().id
            self.overall_progress.remove_task(completed_overall_id)

    def _add_task_result(self, task_result: TaskResult) -> None:
        """Append statistics of media file download result."""
        if task_result == TaskResult.SUCCESS:
            self.num_success += 1
        elif task_result == TaskResult.FAILURE:
            self.num_failure += 1
        elif task_result == TaskResult.SKIPPED:
            self.num_skipped += 1

    # Static methods
    @staticmethod
    def _adjust_description(description: str, max_length: int = 8) -> str:
        """Truncate a string to a specified maximum length adding an ellipsis."""
        return (
            description[:max_length] + "..."
            if len(description) > max_length
            else description
        )

    @staticmethod
    def _create_progress_bar(
        columns: list[Column] | None = None, *, show_time: bool = False,
    ) -> Progress:
        """Create and returns a progress bar for tracking download progress."""
        if columns is None:
            columns = [
                SpinnerColumn(),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            ]

        if show_time:
            columns += [PROGRESS_COLUMNS_SEPARATOR, TimeRemainingColumn()]

        return Progress("{task.description}", *columns)
