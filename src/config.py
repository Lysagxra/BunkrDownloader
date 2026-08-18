"""Configuration module for managing constants and settings used across the project.

These configurations aim to improve modularity and readability by consolidating settings
into a single location.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

import tomllib

from .enums import HTTPStatus

if TYPE_CHECKING:
    from argparse import Namespace


# ============================
# Paths and Files
# ============================
BACKUP_FOLDER = "Backups"      # The folder where backup files will be stored.
DOWNLOAD_FOLDER = "Downloads"  # The folder where downloaded files will be stored.
URLS_FILE = "URLs.txt"         # The file containing the list of URLs to process.
SESSION_LOG = "session.log"    # The file used to log errors.
STATE_FILE = ".bunkr_state.json"

# ============================
# API / Status Endpoints
# ============================
STATUS_PAGE = "https://status.bunkr.ru/"          # Service status page.
BUNKR_API = "https://glb-apisign.cdn.cr/sign"     # Signature API endpoint.
DOWNLOAD_API = "https://dl.bunkr.cr/api/_001_v2"  # Download API endpoint.
DOWNLOAD_REFERER = "https://dl.bunkrr.cr/"        # Referer used for downloads requests.
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

# Constants for file sizes, expressed in bytes.
KB = 1024
MB = 1024 * KB
GB = 1024 * MB

# Thresholds for file sizes and corresponding chunk sizes used during download.
CHUNK_SIZE_THRESHOLDS = [
    (1 * MB, 32 * KB),    # Less than 1 MB
    (10 * MB, 128 * KB),  # 1 MB to 10 MB
    (50 * MB, 512 * KB),  # 10 MB to 50 MB
    (100 * MB, 1 * MB),   # 50 MB to 100 MB
    (250 * MB, 2 * MB),   # 100 MB to 250 MB
    (500 * MB, 4 * MB),   # 250 MB to 500 MB
    (1 * GB, 8 * MB),     # 500 MB to 1 GB
]

# Default chunk size for files larger than the largest threshold.
DEFAULT_CHUNK_SIZE = 16 * MB

# Minimum file size required to trigger a parallel chunked download.
MIN_PARALLEL_SIZE = 64 * MB

# Minimum free disk space required.
MIN_DISK_SPACE = 4 * GB

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
# Mapping of HTTP error codes to human-readable fetch error messages.
FETCH_ERROR_MESSAGES: dict[HTTPStatus, str] = {
    HTTPStatus.FORBIDDEN: "DDoSGuard blocked the request to {url}",
    HTTPStatus.INTERNAL_ERROR: "Internal server error when fetching {url}",
    HTTPStatus.BAD_GATEWAY: "Bad gateway for {url}, probably offline",
}

# Headers used for general HTTP requests.
DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0"
    ),
}

# Headers specifically tailored for download requests.
DOWNLOAD_HEADERS: dict[str, str] = {
    **DEFAULT_HEADERS,
    "Connection": "keep-alive",
    "Referer": DOWNLOAD_REFERER,
}

# ============================
# Config file (bunkr.toml)
# ============================
# Maps each overridable CLI dest name to (built-in default, type validator). Precedence
# when resolving the final value: explicit CLI flag > bunkr.toml value > built-in
# default below. All CLI args participating in this need default=None so an unset flag
# can be distinguished from an explicit one.
_CONFIG_FIELDS: dict[str, tuple[object, object]] = {
    "custom_path": (None, lambda v: isinstance(v, str)),
    "no_download_folder": (False, lambda v: isinstance(v, bool)),
    "no_album_folder": (False, lambda v: isinstance(v, bool)),
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
        logging.warning("Warning: could not read config file '%s': %s", path, exc)
        return {}


def apply_config_file_defaults(args: Namespace) -> Namespace:
    """Fill any CLI flag left unset (None) from bunkr.toml, then built-ins.

    Precedence: explicit CLI flag > bunkr.toml value > built-in default. Only mutates
    attributes that already exist on `args` — parsers that don't include a given option
    (e.g. --ignore/--include in common_only mode) are left untouched. Unknown TOML keys
    are ignored. A TOML value with the wrong type is ignored (with a warning) in favor
    of the built-in default, rather than letting a bad config crash the program.
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

            logging.warning(
                "Warning: bunkr.toml '%s' has an invalid value (%r); "
                "using the default instead.",
                key,
                value,
            )

        setattr(args, key, builtin_default)

    return args
