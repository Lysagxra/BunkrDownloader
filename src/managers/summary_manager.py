"""Task execution summary management.

This module provides the SummaryManager class, which is responsible for tracking and
aggregating task execution results (completed, failed, skipped) and their associated
reasons using counters.
"""

from collections import Counter
from enum import IntEnum

from src.config import (
    TASK_REASON_MAPPING,
    CompletedReason,
    FailedReason,
    SkippedReason,
    TaskReason,
    TaskResult,
)


class SummaryManager:
    """Manage aggregated statistics for task execution results."""

    def __init__(self) -> None:
        """Initialize empty counters for all task results and reasons."""
        self._result_counts: dict[TaskResult, Counter[TaskReason]] = {
            TaskResult.COMPLETED: Counter(),
            TaskResult.FAILED: Counter(),
            TaskResult.SKIPPED: Counter(),
        }

    def get_result_count(
        self,
        task_result: TaskResult,
        reason: IntEnum = TaskReason.REASON_ALL,
    ) -> int:
        """Return the count of tasks with the specified result and a reason."""
        return self._result_counts[task_result][reason]

    def update_result(self, task_reason: IntEnum) -> None:
        """Update the task result statistics based on the provided task reason."""
        task_result = self._get_task_result(task_reason)
        reason_class = TASK_REASON_MAPPING.get(task_result)

        if not isinstance(task_reason, reason_class):
            log_message = (
                f"Invalid reason type for {task_reason}: "
                f"expected {reason_class.__name__}, "
                f"got {type(task_reason).__name__}."
            )
            raise TypeError(log_message)

        self._result_counts[task_result][task_reason] += 1
        self._result_counts[task_result][TaskReason.REASON_ALL] += 1

    def _get_task_result(self, task_reason: IntEnum) -> TaskResult:
        """Determina a quale TaskResult appartiene il task_reason."""
        if isinstance(task_reason, CompletedReason):
            return TaskResult.COMPLETED

        if isinstance(task_reason, FailedReason):
            return TaskResult.FAILED

        if isinstance(task_reason, SkippedReason):
            return TaskResult.SKIPPED

        log_message = f"Unknown task reason type: {task_reason}"
        raise ValueError(log_message)
