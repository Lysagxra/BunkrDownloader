"""Application-wide configuration, constants, and data models.

This module centralizes shared settings, enumerations, and data structures used
throughout the application.
"""

from enum import IntEnum, auto


class UrlType(IntEnum):
    """Enumerate the supported Bunkr URL types."""

    ALBUM = auto()
    MEDIA = auto()

class HTTPStatus(IntEnum):
    """Enumeration of common HTTP status codes used in the project."""

    OK = 200
    FORBIDDEN = 403
    TOO_MANY_REQUESTS = 429
    INTERNAL_ERROR = 500
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503
    SERVER_DOWN = 521

# ============================
# Results Summary
# ============================
class TaskResult(IntEnum):
    """Enumerate the possible outcomes for a processed task."""

    COMPLETED = auto()  # The task completed successfully.
    FAILED = auto()     # The task failed due to an error.
    SKIPPED = auto()    # The task was intentionally skipped.

class TaskReason(IntEnum):
    """Enumerate the possible reasons per each task result."""

    ALL = -1  # The total count of tasks per any group.

class CompletedReason(IntEnum):
    """Enumerate the possible reasons for a completed task."""

    DOWNLOAD_SUCCESS = 1

class FailedReason(IntEnum):
    """Enumerate the possible reasons for a failed task."""

    MAX_RETRIES_REACHED = 1

class SkippedReason(IntEnum):
    """Enumerate the possible reasons for a skipped task."""

    ALREADY_DOWNLOADED = auto()
    IGNORE_LIST = auto()
    INCLUDE_LIST = auto()
    DOMAIN_OFFLINE = auto()
    SERVICE_UNAVAILABLE = auto()

TASK_REASON_MAPPING: dict[TaskResult, type[IntEnum]] = {
    TaskResult.COMPLETED: CompletedReason,
    TaskResult.FAILED: FailedReason,
    TaskResult.SKIPPED: SkippedReason,
}
