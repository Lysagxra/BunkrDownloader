"""Data models and state containers used throughout the application."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .config import BUFFER_SIZE, MAX_RETRIES, PROGRESS_MANAGER_COLORS
from .enums import UrlType

if TYPE_CHECKING:
    import asyncio
    from argparse import Namespace
    from datetime import datetime
    from pathlib import Path

    from bs4 import BeautifulSoup

    from src.managers.rate_limiter import RateLimiter


@dataclass
class AlbumInfo:
    """Store the information about an album and its associated item pages."""

    album_id: str
    item_pages: list[str]
    item_dates: dict[str, datetime | None] = field(default_factory=dict)
    cached_items: dict[str, dict] = field(default_factory=dict)

@dataclass
class DownloadInfo:
    """Represent the information related to a download task."""

    item_url: str
    download_link: str
    filename: str
    task: int
    item_date: datetime | None = None

@dataclass
class SessionInfo:
    """Hold the session-related information."""

    args: Namespace | None
    bunkr_status: dict[str, str]
    download_path: str
    rate_limiter: RateLimiter | None = None

@dataclass(frozen=True, slots=True)
class UrlInfo:
    """Information about a resolved Bunkr URL."""

    url: str
    url_type: UrlType
    soup: BeautifulSoup

    @property
    def is_album(self) -> bool:
        """Return whether the URL points to an album."""
        return self.url_type is UrlType.ALBUM

    @property
    def is_media(self) -> bool:
        """Return whether the URL points to a single media."""
        return self.url_type is UrlType.MEDIA

# Map URL identifiers to their corresponding URL type.
URL_TYPE_MAPPING: dict[str, UrlType] = {
    "a": UrlType.ALBUM,
    "f": UrlType.MEDIA,
    "i": UrlType.MEDIA,
    "v": UrlType.MEDIA,
}

@dataclass(slots=True)
class ChunkInfo:
    """Configuration and callbacks required to download file chunks."""

    headers: dict[str, str]
    on_progress: callable
    rate_limiter: RateLimiter | None = None

@dataclass(frozen=True)
class ItemInfo:
    """Information required to download an item."""

    page: str
    filename: str
    download_link: str
    date: datetime | None = None

@dataclass
class ResolveContext:
    """Context shared while resolving items."""

    session_info: SessionInfo
    cached_items: dict[str, dict]
    item_dates: dict[str, datetime | None]
    semaphore: asyncio.Semaphore
    reserved_names: set[str]
    reservation_lock: asyncio.Lock

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
    panel_width: int = 40
    overall_buffer: deque[str] = field(
        default_factory=lambda: deque(maxlen=BUFFER_SIZE),
    )

@dataclass(frozen=True)
class DownloadPlan:
    """Describe how a file should be downloaded in chunks."""

    ranges: list[tuple[int, int]]
    num_ranges: int
    chunk_paths: list[Path]
    expected_sizes: list[int]

@dataclass
class DownloadState:
    """Track mutable state accumulated during an album download."""

    failed_downloads: list = field(default_factory=list)
    unresolved_failures: int = 0
    cached_items: dict[str, dict] = field(default_factory=dict)
