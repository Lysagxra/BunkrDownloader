"""Configuration module for managing constants and settings used across the project.

These configurations aim to improve modularity and readability by consolidating settings
into a single location.
"""

from __future__ import annotations

import logging
import re
from argparse import ArgumentParser
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING

import tomllib  # Python 3.11+ standard library

from .version import get_version_string

if TYPE_CHECKING:
    from argparse import Namespace

    from .rate_limiter import RateLimiter


# ============================
# Paths and Files
# ============================
BACKUP_FOLDER = "Backups"      # The folder where backup files will be stored.
DOWNLOAD_FOLDER = "Downloads"  # The folder where downloaded files will be stored.
URLS_FILE = "URLs.txt"         # The file containing the list of URLs to process.
SESSION_LOG = "session.log"    # The file used to log errors.
MIN_DISK_SPACE_GB = 3          # Minimum free disk space (in GB) required.

# ============================
# API / Status Endpoints
# ============================
STATUS_PAGE = "https://status.bunkr.ru/"          # Service status page.
BUNKR_API = "https://glb-apisign.cdn.cr/sign"     # Signature API endpoint.
DOWNLOAD_API = "https://dl.bunkr.cr/api/_001_v2"  # Download API endpoint.
DOWNLOAD_REFERER = "https://get.bunkrr.su/"       # Referer used for downloads requests.
FALLBACK_DOMAIN = "bunkr.cr"                      # Default fallback domain.

# ============================
# Regex Patterns
# ============================
MEDIA_SLUG_REGEX = r'const\s+slug\s*=\s*"([a-zA-Z0-9_-]+)"'  # Extract media slug.
VALID_SLUG_REGEX = r"^[a-zA-Z0-9_-]+$"                       # Validate media slug.
VALID_CHARACTERS_REGEX = r'[<>:"/\\|?*\x00-\x1f]'            # Validate characters.
JS_VARS_REGEX = r'var\s+(\w+)\s*=\s*(".*?"|\'.*?\'|[^;]+);'  # Extract JS variable.
JS_VARS_COMP = re.compile(JS_VARS_REGEX, re.DOTALL)          # Compiled regex.

# ============================
# UI & Table Settings
# ============================
BUFFER_SIZE = 5                   # Maximum number of items showed in buffers.
PROGRESS_COLUMNS_SEPARATOR = "•"  # Visual separator used between progress bar columns.
REFRESH_PER_SECOND = 10           # Number of screen refreshes per second.

# Colors used for the progress manager UI elements
PROGRESS_MANAGER_COLORS = {
    "title_color": "light_cyan3",           # Title color for progress panels.
    "overall_border_color": "bright_blue",  # Border color for overall progress panel.
    "task_border_color": "medium_purple",   # Border color for task progress panel.
}

# Setting used for the log manager UI elements
LOG_MANAGER_CONFIG = {
    "colors": {
        "title_color": "light_cyan3",  # Title color for log panel.
        "border_color": "cyan",        # Border color for log panel.
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
MAX_FILENAME_LEN = 120   # The maximum length for a file name.
MAX_WORKERS = 3          # The maximum number of threads for concurrent downloads.
MAX_RETRIES = 5          # The maximum number of retries for downloading a single media.
DEFAULT_CONNECTIONS = 4  # Default number of parallel connections for chunked downloads.
CHUNK_MAX_RETRIES = 4    # Max retry attempts for a single failed chunk.
CHUNK_BASE_DELAY = 1.5   # Base delay (seconds) for chunk retry exponential backoff.

# Mapping of URL identifiers to a boolean for album (True) vs single file (False).
URL_TYPE_MAPPING = {"a": True, "f": False, "i": False, "v": False}

# Constants for file sizes, expressed in bytes.
KB = 1024
MB = 1024 * KB
GB = 1024 * MB

# Thresholds for file sizes and corresponding chunk sizes used during download.
THRESHOLDS = [
    (1 * MB, 32 * KB),    # Less than 1 MB
    (10 * MB, 128 * KB),  # 1 MB to 10 MB
    (50 * MB, 512 * KB),  # 10 MB to 50 MB
    (100 * MB, 1 * MB),   # 50 MB to 100 MB
    (250 * MB, 2 * MB),   # 100 MB to 250 MB
    (500 * MB, 4 * MB),   # 250 MB to 500 MB
    (1 * GB, 8 * MB),     # 500 MB to 1 GB
]

# Default chunk size for files larger than the largest threshold.
LARGE_FILE_CHUNK_SIZE = 16 * MB

# Minimum file size required to trigger a parallel chunked download.
MIN_PARALLEL_SIZE = 5 * MB

# ============================
# Work-stealing unit sizing
# ============================
# Split the file into more work units than available connections. ThreadPoolExecutor
# assigns the next pending unit to each free worker, providing dynamic load balancing: a
# slow worker only affects its current unit instead of delaying the entire download.
UNITS_PER_CONNECTION = 4        # Target oversubscription factor.
MIN_WORK_UNIT_SIZE = 4 * MB     # Floor: avoids excessive tiny-file overhead.
MAX_WORK_UNIT_SIZE = 64 * MB    # Ceiling: keeps granularity meaningful.

# ============================
# HTTP / Network
# ============================
class HTTPStatus(IntEnum):
    """Enumeration of common HTTP status codes used in the project."""

    OK = 200
    FORBIDDEN = 403
    TOO_MANY_REQUESTS = 429
    INTERNAL_ERROR = 500
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503
    SERVER_DOWN = 521

# Mapping of HTTP error codes to human-readable fetch error messages.
FETCH_ERROR_MESSAGES: dict[HTTPStatus, str] = {
    HTTPStatus.FORBIDDEN: "DDoSGuard blocked the request to {url}",
    HTTPStatus.INTERNAL_ERROR: "Internal server error when fetching {url}",
    HTTPStatus.BAD_GATEWAY: "Bad gateway for {url}, probably offline",
}

# Headers used for general HTTP requests.
HEADERS : dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0"
    ),
}

# Headers specifically tailored for download requests.
DOWNLOAD_HEADERS: dict[str, str] = {
    **HEADERS,
    "Connection": "keep-alive",
    "Referer": DOWNLOAD_REFERER,
}

# ============================
# Data Classes
# ============================
@dataclass
class AlbumInfo:
    """Store the information about an album and its associated item pages."""

    album_id: str
    item_pages: list[str]

@dataclass
class DownloadInfo:
    """Represent the information related to a download task."""

    item_url: str
    download_link: str
    filename: str
    task: int

@dataclass
class SessionInfo:
    """Hold the session-related information."""

    args: Namespace | None
    bunkr_status: dict[str, str]
    download_path: str
    rate_limiter: RateLimiter | None = None

@dataclass(slots=True)
class ChunkInfo:
    """Configuration and callbacks required to download file chunks."""

    headers: dict[str, str]
    on_progress: callable
    rate_limiter: RateLimiter | None = None

@dataclass(slots=True)
class DownloadConfig:
    """Configuration required to download a file."""

    content_length: int
    num_connections: int
    headers: dict[str, str]
    rate_limiter: RateLimiter | None = None

@dataclass(slots=True)
class RetryConfig:
    """Retry behavior configuration."""

    retries: int = MAX_RETRIES
    # True when an external caller retries failures; False for standalone downloads.
    has_external_retry: bool = False

@dataclass
class ProgressConfig:
    """Configuration for progress bar settings."""

    task_name: str
    item_description: str
    color: str = PROGRESS_MANAGER_COLORS["title_color"]
    panel_width = 40
    overall_buffer: deque = field(default_factory=lambda: deque(maxlen=BUFFER_SIZE))

# ============================
# Results Summary
# ============================
class TaskResult(IntEnum):
    """Enumerate the possible outcomes for a processed task."""

    COMPLETED = 1  # The task completed successfully.
    FAILED = 2     # The task failed due to an error.
    SKIPPED = 3    # The task was intentionally skipped.

class TaskReason(IntEnum):
    """Enumerate the possible reasons per each task result."""

    REASON_ALL = -1  # The total count of tasks per any group.

class CompletedReason(IntEnum):
    """Enumerate the possible reasons for a completed task."""

    DOWNLOAD_SUCCESS = 1

class FailedReason(IntEnum):
    """Enumerate the possible reasons for a failed task."""

    MAX_RETRIES_REACHED = 1

class SkippedReason(IntEnum):
    """Enumerate the possible reasons for a skipped task."""

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
# Config file (bunkr.toml)
# ============================
# Maps each overridable CLI dest name to (built-in default, type validator).
# Precedence when resolving the final value: explicit CLI flag > bunkr.toml
# value > built-in default below. All CLI args participating in this need
# default=None so an unset flag can be distinguished from an explicit one.
_CONFIG_FIELDS: dict[str, tuple[object, object]] = {
    "custom_path": (None, lambda v: isinstance(v, str)),
    "no_download_folder": (False, lambda v: isinstance(v, bool)),
    "disable_ui": (False, lambda v: isinstance(v, bool)),
    "disable_disk_check": (False, lambda v: isinstance(v, bool)),
    "max_retries": (
        MAX_RETRIES, lambda v: isinstance(v, int) and not isinstance(v, bool),
    ),
    "connections": (
        DEFAULT_CONNECTIONS, lambda v: isinstance(v, int) and not isinstance(v, bool),
    ),
    "rate_limit": (
        None, lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    ),
    "dry_run": (False, lambda v: isinstance(v, bool)),
    "max_concurrent_urls": (
        1, lambda v: isinstance(v, int) and not isinstance(v, bool),
    ),
    "ignore": (
        None, lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
    ),
    "include": (
        None, lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
    ),
}


def _find_config_file(explicit_path: str | None) -> Path | None:
    """Resolve the bunkr.toml path: explicit --config, else cwd/bunkr.toml."""
    if explicit_path:
        path = Path(explicit_path)
        return path if path.is_file() else None

    default_path = Path.cwd() / "bunkr.toml"
    return default_path if default_path.is_file() else None


def _load_toml_config(path: Path) -> dict:
    """Load a TOML config file, returning {} on any read/parse failure."""
    try:
        with path.open("rb") as file:
            return tomllib.load(file)

    except (OSError, tomllib.TOMLDecodeError) as exc:
        log_message = f"Warning: could not read config file '{path}': {exc}"
        logging.warning(log_message)
        return {}


def apply_config_file_defaults(args: Namespace) -> Namespace:
    """Fill any CLI flag left unset (None) from bunkr.toml, then built-ins.

    Precedence: explicit CLI flag > bunkr.toml value > built-in default.
    Only mutates attributes that already exist on `args` — parsers that
    don't include a given option (e.g. --ignore/--include in common_only
    mode) are left untouched. Unknown TOML keys are ignored. A TOML value
    with the wrong type is ignored (with a warning) in favor of the
    built-in default, rather than letting a bad config crash the program.
    """
    config_path = _find_config_file(getattr(args, "config", None))
    toml_data = _load_toml_config(config_path) if config_path else {}

    for key, (builtin_default, is_valid) in _CONFIG_FIELDS.items():
        if not hasattr(args, key):
            continue  # this parser variant doesn't expose this option

        if getattr(args, key) is not None:
            continue  # explicitly set via CLI -- config file never overrides it

        if key in toml_data:
            value = toml_data[key]
            if is_valid(value):
                setattr(args, key, value)
                continue

            log_message = (
                f"Warning: bunkr.toml '{key}' has an invalid value ({value!r}); "
                "using the default instead.",
            )
            logging.warning(log_message)

        setattr(args, key, builtin_default)

    return args


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
        default=None,
        help="Save files without a 'Downloads' subfolder.",
    )
    parser.add_argument(
        "--disable-ui",
        action="store_true",
        default=None,
        help="Disable the user interface.",
    )
    parser.add_argument(
        "--disable-disk-check",
        action="store_true",
        default=None,
        help="Disable the disk space check for available free space.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help=f"Maximum number of retries for downloading a single media "
        f"(default: {MAX_RETRIES}).",
    )
    parser.add_argument(
        "--connections",
        type=int,
        default=None,
        help=(
            "Number of parallel connections used for chunked downloads "
            f"(default: {DEFAULT_CONNECTIONS}). Set to 1 to disable chunked "
            "downloading."
        ),
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=None,
        metavar="KB/S",
        help=(
            "Maximum total download speed in KB/s, shared across all "
            "connections and concurrently downloading files "
            "(default: unlimited)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=None,
        help=(
            "List the files that would be downloaded (with sizes and "
            "skip/filter status) without downloading or writing anything."
        ),
    )
    parser.add_argument(
        "--max-concurrent-urls",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Number of URLs from URLs.txt to process concurrently "
            "(default: 1 — sequential, same as before). Values above 1 "
            "disable the live progress UI (falls back to plain log lines) "
            "since the progress display only supports tracking one album "
            "at a time."
        ),
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "Path to a TOML config file providing default values for any "
            "of the above flags (default: looks for ./bunkr.toml). "
            "Explicit CLI flags always take precedence over the config file."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=get_version_string(),
        help="Show program's version and exit.",
    )


def setup_parser(
        *, include_url: bool = False, include_filters: bool = False,
    ) -> ArgumentParser:
    """Set up parser with optional argument groups."""
    parser = ArgumentParser(description="Command-line arguments.")

    if include_url:
        parser.add_argument("url", type=str, help="The URL to process")

    if include_filters:
        parser.add_argument(
            "--ignore",
            type=str,
            nargs="+",
            default=None,
            help="Skip files whose names contain any of these substrings.",
        )
        parser.add_argument(
            "--include",
            type=str,
            nargs="+",
            default=None,
            help="Only download files whose names contain these substrings.",
        )

    add_common_arguments(parser)
    return parser


def parse_arguments(*, common_only: bool = False) -> Namespace:
    """Full argument parser (including URL, filters, and common).

    After parsing, any flag left unset on the command line is filled in
    from bunkr.toml (if present) and finally from built-in defaults — see
    apply_config_file_defaults.
    """
    parser = (
        setup_parser() if common_only
        else setup_parser(include_url=True, include_filters=True)
    )
    args = parser.parse_args()
    return apply_config_file_defaults(args)
