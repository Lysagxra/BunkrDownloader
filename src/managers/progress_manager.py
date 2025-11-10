"""Provide a `ProgressManager` class for tracking and displaying the progress of tasks.

It uses the Rich library to create dynamic, formatted progress bars and tables for
monitoring task completion.
"""

from __future__ import annotations

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
        # Optional one-line status to display under the overall panel title
        self.status_text = None
        # Count of downloads that exceeded their retry limit and will be retried
        # after the main tasks have finished.
        self.post_retry_count = 0

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

    def add_task(self, current_task: int = 0, total: int = 100, base_one: bool = False) -> int:
        """Add an individual task to the task progress bar.

        Parameters:
        - current_task: zero-based index by default. If `base_one` is True,
          `current_task` is interpreted as a 1-based position and displayed
          directly (useful for retry passes where callers prefer to pass 1-based
          positions).
        - total: task total for the individual progress bar.
        - base_one: when True, do not add 1 to `current_task` when building the
          description.
        """
        if base_one:
            disp_current = current_task
        else:
            disp_current = current_task + 1

        task_description = (
            f"[{self.config.color}]{self.config.item_description} "
            f"{disp_current}/{self.num_tasks}"
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

    def create_progress_table(self, min_panel_width: int = 30) -> Table:
        """Create a formatted progress table for tracking the download."""
        terminal_width, _ = shutil.get_terminal_size()
        panel_width = max(min_panel_width, terminal_width // 2)

        progress_table = Table.grid()
        progress_table.add_row(
            Panel.fit(
                self.overall_progress,
                title=f"[bold {self.config.color}]Overall Progress",
                subtitle=self._build_overall_subtitle(),
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

    def set_overall_status(self, status: str | None) -> None:
        """Set a short status line shown under the Overall Progress panel title.

        This is used by callers (for example LiveManager) to display small
        one-line hints such as the session/verbose log paths.
        """
        self.status_text = status

    def increment_post_retry_count(self, amount: int = 1) -> None:
        """Increment the post-task retry counter by `amount` (default 1)."""
        try:
            self.post_retry_count += int(amount)
        except (TypeError, ValueError):
            # If given a bad value, just increment by one as a safe fallback
            self.post_retry_count += 1

    def reset_post_retry_count(self) -> None:
        """Reset the post-task retry counter to zero."""
        self.post_retry_count = 0

    def set_post_retry_count(self, value: int) -> None:
        """Set the post-task retry counter to a specific integer value."""
        try:
            self.post_retry_count = max(0, int(value))
        except (TypeError, ValueError):
            # Ignore invalid values and leave the counter unchanged
            pass

    def _build_overall_subtitle(self) -> str:
        """Return the formatted subtitle for the overall panel including status and retry count."""
        base = self.status_text or ""
        retry_part = f"Post task retries: {self.post_retry_count}"
        if base:
            return f"{base}  {retry_part}"
        return retry_part

    # Private methods
    def _update_overall_task(self, task_id: int) -> None:
        """Advance the overall progress bar and removes old tasks."""
        if not self.overall_progress.tasks:
            return

        if task_id < 0 or task_id >= len(self.task_progress.tasks):
            return

        # Access the latest overall task dynamically
        current_overall_task = self.overall_progress.tasks[-1]

        # If the task is finished, remove it and update the overall progress
        try:
            if self.task_progress.tasks[task_id].finished:
                self.overall_progress.advance(current_overall_task.id)
                self.task_progress.update(task_id, visible=False)
        except Exception:
            # Guard against race conditions where tasks disappear concurrently
            return

        # Track completed overall tasks
        try:
            if current_overall_task.finished:
                self.config.overall_buffer.append(current_overall_task)
        except Exception:
            pass

        # Cleanup completed overall tasks
        self._cleanup_completed_overall_tasks()

    def _cleanup_completed_overall_tasks(self) -> None:
        """Remove the oldest completed overall task from the buffer and progress bar."""
        if len(self.config.overall_buffer) == self.config.overall_buffer.maxlen:
            completed_overall_id = self.config.overall_buffer.popleft().id
            self.overall_progress.remove_task(completed_overall_id)

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
            # Use an ASCII-safe spinner to avoid terminal glyph issues
            columns = [
                SpinnerColumn(spinner_name="line"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            ]

        if show_time:
            columns += [PROGRESS_COLUMNS_SEPARATOR, TimeRemainingColumn()]

        return Progress("{task.description}", *columns)

    # Accessor methods for external consumers like LiveManager
    def get_total_tasks(self) -> int:
        """Return the configured total number of overall tasks."""
        return int(self.num_tasks or 0)

    def get_completed_tasks(self) -> int:
        """Return the number of completed overall tasks tracked by the progress bar."""
        try:
            return sum(1 for t in self.overall_progress.tasks if t.finished)
        except Exception:
            return 0

    def get_post_retry_count(self) -> int:
        """Return the post-retry counter value."""
        try:
            return int(self.post_retry_count)
        except Exception:
            return 0
