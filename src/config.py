"""Configuration module for managing constants and settings used across the project."""

from __future__ import annotations

import os
from argparse import ArgumentParser
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace

# ============================
# Paths and Files
# ============================
BACKUP_FOLDER = "Backups"
DOWNLOAD_FOLDER = "Downloads"
URLS_FILE = "URLs.txt"
SESSION_LOG = "session.log"
MIN_DISK_SPACE_GB = 3

# ============================
# API / Status Endpoints
# ============================
STATUS_PAGE = "https://status.bunkr.ru/"
BUNKR_API = "https://bunkr.cr/api/vs"
FALLBACK_DOMAIN = "bunkr.cr"
DOWNLOAD_REFERER = "https://get.bunkrr.su/"

# ============================
# Regex Patterns
# ============================
MEDIA_SLUG_REGEX = r'const\s+slug\s*=\s*"([a-zA-Z0-9_-]+)"'
VALID_SLUG_REGEX = r"^[a-zA-Z0-9_-]+$"
VALID_CHARACTERS_REGEX = r'[<>:"/\\|?*\x00-\x1f]'

# ============================
# UI & Table Settings
# ============================
BUFFER_SIZE = 5
PROGRESS_COLUMNS_SEPARATOR = "•"
REFRESH_PER_SECOND = 10

PROGRESS_MANAGER_COLORS = {
    "title_color": "light_cyan3",
    "overall_border_color": "bright_blue",
    "task_border_color": "medium_purple",
}

LOG_MANAGER_CONFIG = {
    "colors": {
        "title_color": "light_cyan3",
        "border_color": "cyan",
    },
    "min_column_widths": {
        "Timestamp": 10,
        "Event": 15,
        "Details": 30,
    },
    "column_styles": {
        "Timestamp": "pale_turquoise4",
        "Event": "pale_turquoise1",
        "Details": "pale_turquoise4",
    },
}

# ============================
# Download Settings
# ============================
MAX_FILENAME_LEN = 120
MAX_WORKERS = 3
MAX_RETRIES = 5

URL_TYPE_MAPPING = {"a": True, "f": False, "i": False, "v": False}

KB = 1024
MB = 1024 * KB
GB = 1024 * MB

THRESHOLDS = [
    (1 * MB, 32 * KB),
    (10 * MB, 128 * KB),
    (50 * MB, 512 * KB),
    (100 * MB, 1 * MB),
    (250 * MB, 2 * MB),
    (500 * MB, 4 * MB),
    (1 * GB, 8 * MB),
]

LARGE_FILE_CHUNK_SIZE = 16 * MB

# ============================
# HTTP / Network
# ============================
class HTTPStatus(IntEnum):
    OK = 200
    FORBIDDEN = 403
    TOO_MANY_REQUESTS = 429
    INTERNAL_ERROR = 500
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503
    SERVER_DOWN = 521

FETCH_ERROR_MESSAGES: dict[HTTPStatus, str] = {
    HTTPStatus.FORBIDDEN: "DDoSGuard blocked the request to {url}",
    HTTPStatus.INTERNAL_ERROR: "Internal server error when fetching {url}",
    HTTPStatus.BAD_GATEWAY: "Bad gateway for {url}, probably offline",
}

HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0"
    ),
}

DOWNLOAD_HEADERS: dict[str, str] = {
    **HEADERS,
    "Connection": "keep-alive",
    "Referer": DOWNLOAD_REFERER,
}

# ============================
# Path Resolution Helper
# ============================
def resolve_download_path(args: Namespace) -> str:
    """Centralized path resolution to strip duplication across scripts."""
    base_dir = args.custom_path if args.custom_path else "."
    if args.no_download_folder and args.custom_path:
        return base_dir
    return os.path.join(base_dir, DOWNLOAD_FOLDER)

# ============================
# Data Classes
# ============================
@dataclass
class AlbumInfo:
    album_id: str
    item_pages: list[str]

@dataclass
class DownloadInfo:
    item_url: str
    download_link: str
    filename: str
    task: int

@dataclass
class SessionInfo:
    args: Namespace | None
    bunkr_status: dict[str, str]
    download_path: str

@dataclass
class ProgressConfig:
    task_name: str
    item_description: str
    color: str = PROGRESS_MANAGER_COLORS["title_color"]
    panel_width = 40
    overall_buffer: deque = field(default_factory=lambda: deque(maxlen=BUFFER_SIZE))

# ============================
# Results Summary
# ============================
class TaskResult(IntEnum):
    COMPLETED = 1
    FAILED = 2
    SKIPPED = 3

class TaskReason(IntEnum):
    REASON_ALL = -1

class CompletedReason(IntEnum):
    DOWNLOAD_SUCCESS = 1

class FailedReason(IntEnum):
    MAX_RETRIES_REACHED = 1

class SkippedReason(IntEnum):
    ALREADY_DOWNLOADED = 1
    IGNORE_LIST = 2
    INCLUDE_LIST = 3
    DOMAIN_OFFLINE = 4
    SERVICE_UNAVAILABLE = 5

TASK_REASON_MAPPING: dict[TaskResult, type[IntEnum]] = {
    TaskResult.COMPLETED: CompletedReason,
    TaskResult.FAILED: FailedReason,
    TaskResult.SKIPPED: SkippedReason,
}

# ============================
# Argument Parsing
# ============================
def add_common_arguments(parser: ArgumentParser) -> None:
    """Add arguments shared across parsers."""
    parser.add_argument(
        "--custom-path",
        type=str,
        default=None,
        help="The directory where the downloaded content will be saved.",
    )
    parser.add_argument(
        "--no-download-folder",
        action="store_true",
        help="If using --custom-path, save files directly in that directory without creating a 'Downloads' subfolder.",
    )
    parser.add_argument(
        "--disable-ui",
        action="store_true",
        help="Disable the user interface.",
    )
    parser.add_argument(
        "--disable-disk-check",
        action="store_true",
        help="Disable the disk space check for available free space.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=MAX_RETRIES,
        help="Maximum number of retries for downloading a single media.",
    )

def setup_parser(
        *, include_url: bool = False, include_filters: bool = False,
    ) -> ArgumentParser:
    """Set up parser with optional argument groups."""
    parser = ArgumentParser(description="Bunkr Downloader - CLI")

    if include_url:
        parser.add_argument("url", type=str, help="The URL to process")

    if include_filters:
        parser.add_argument(
            "--ignore",
            type=str,
            nargs="+",
            help="[NEGATIVE PROMPT] Skip files containing these substrings.",
        )
        parser.add_argument(
            "--include",
            type=str,
            nargs="+",
            help="[POSITIVE PROMPT] Only download files matching these substrings.",
        )

    add_common_arguments(parser)
    return parser

def parse_arguments(*, common_only: bool = False) -> Namespace:
    """Full argument parser (including URL, filters, and common)."""
    parser = (
        setup_parser(include_filters=True) if common_only
        else setup_parser(include_url=True, include_filters=True)
    )
    return parser.parse_args()