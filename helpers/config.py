"""Configuration module for managing constants and settings used across the project.

These configurations aim to improve modularity and readability by consolidating settings
into a single location.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace


# ============================
# Paths and Files
# ============================
DOWNLOAD_FOLDER = "Downloads"    # The folder where downloaded files will be stored.
URLS_FILE = "URLs.txt"           # The file containing the list of URLs to process.
SESSION_LOG = "session_log.txt"  # The file used to log errors.
MIN_DISK_SPACE_GB = 3            # Minimum free disk space (in GB) required.

# ============================
# API / Status Endpoints
# ============================
STATUS_PAGE = "https://status.bunkr.ru/"  # The URL of the status page for checking
                                          # service availability.
BUNKR_API = "https://bunkr.cr/api/vs"     # The API for retrieving encryption data.

# ============================
# Regex Patterns
# ============================
MEDIA_SLUG_REGEX = r'const\s+slug\s*=\s*"([a-zA-Z0-9_-]+)"'  # Extract media slug.
VALID_SLUG_REGEX = r"^[a-zA-Z0-9_-]+$"                       # Validate media slug.

# ============================
# Download Settings
# ============================
MAX_FILENAME_LEN = 120  # The maximum length for a file name.
MAX_WORKERS = 3         # The maximum number of threads for concurrent downloads.

# Mapping of URL identifiers to a boolean for album (True) vs single file (False).
URL_TYPE_MAPPING = {"a": True, "f": False, "v": False}

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
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0"
    ),
}

# Headers specifically tailored for download requests.
DOWNLOAD_HEADERS = {
    **HEADERS,
    "Connection": "keep-alive",
    "Referer": "https://get.bunkrr.su/",
}

# ============================
# Data Classes
# ============================
@dataclass
class DownloadInfo:
    """Represent the information related to a download task."""

    download_link: str
    filename: str
    task: int

@dataclass
class SessionInfo:
    """Hold the session-related information."""

    args: Namespace | None
    bunkr_status: dict[str, str]
    download_path: str

@dataclass
class AlbumInfo:
    """Store the information about an album and its associated item pages."""

    album_id: str
    item_pages: list[str]
