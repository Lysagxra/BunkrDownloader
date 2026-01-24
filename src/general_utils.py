"""Utilities for fetching pages, managing directories, and clearing the terminal.

It includes functions to handle common tasks such as sending HTTP requests, parsing
HTML, creating download directories, and clearing the terminal, making it reusable
across projects.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import random
import shutil
import sys
from http.client import RemoteDisconnected
from pathlib import Path
from typing import TYPE_CHECKING

import requests
from bs4 import BeautifulSoup
from requests import Response

from .config import (
    DOWNLOAD_HEADERS,
    FETCH_ERROR_MESSAGES,
    MIN_DISK_SPACE_GB,
    HTTPStatus,
)
from .file_utils import write_on_session_log
from .url_utils import replace_domain_with_fallback

if TYPE_CHECKING:
    from src.managers.live_manager import LiveManager


def validate_download_link(download_link: str) -> bool:
    """Check if a download link is accessible."""
    try:
        response = requests.head(download_link, headers=DOWNLOAD_HEADERS, timeout=5)

    except requests.RequestException:
        return False

    return response.status_code != HTTPStatus.SERVER_DOWN


async def fetch_page(url: str, retries: int = 5) -> BeautifulSoup | None:
    """Fetch the HTML content of a page at the given URL, with retry logic."""
    tried_cr = False

    def handle_response(response: Response) -> BeautifulSoup | None:
        """Process the HTTP response and handles specific status codes."""
        if response.status_code in FETCH_ERROR_MESSAGES:
            log_message = FETCH_ERROR_MESSAGES[response.status_code].format(url=url)
            logging.exception(log_message)
            write_on_session_log(url)
            return None

        return BeautifulSoup(response.text, "html.parser")

    for attempt in range(retries):
        try:
            response = requests.Session().get(url, timeout=40)
            if response.status_code == HTTPStatus.FORBIDDEN and not tried_cr:
                tried_cr = True
                url = replace_domain_with_fallback(url)
                continue  # Retry immediately with .cr

            response.raise_for_status()
            return handle_response(response)

        # Connection dropped unexpectedly by the server
        except RemoteDisconnected:
            logging.exception("Remote end closed connection without response.")
            if attempt < retries - 1:
                # Add jitter to avoid a retry storm
                delay = 2 ** (attempt + 1) + random.uniform(1, 2)  # noqa: S311
                await asyncio.sleep(delay)

        # Catch-all for request-related errors
        except requests.RequestException as req_err:
            log_message = f"Request error for {url}: {req_err}"
            logging.exception(log_message)
            return None

    return None


def clear_terminal() -> None:
    """Clear the terminal screen based on the operating system."""
    commands = {
        "nt": "cls",       # Windows
        "posix": "clear",  # macOS and Linux
    }

    command = commands.get(os.name)
    if command:
        os.system(command)  # noqa: S605


def check_python_version(min_version: tuple[int, int] = (3, 10)) -> None:
    """Check if the current Python version meets the minimum requirement."""
    current_version = sys.version_info
    if current_version < min_version:
        log_message = (
            f"Python {current_version.major}.{current_version.minor} is not supported. "
            f" Python {min_version[0]}.{min_version[1]} or higher is required.",
        )
        logging.warning(log_message)
        sys.exit(1)


def get_root_path() -> str:
    """Return the filesystem root for the current working directory."""
    cwd = Path.cwd()
    if platform.system() == "Windows":
        return os.path.splitdrive(cwd)[0] + "\\"

    # Use actual working directory
    return cwd


def check_disk_space(live_manager: LiveManager, custom_path: str | None = None) -> None:
    """Check if the available disk space is greater than or equal to `min_space` GB."""
    root_path = get_root_path() if custom_path is None else custom_path
    _, _, free_space = shutil.disk_usage(root_path)
    free_space_gb = free_space / (1024 ** 3)

    if free_space_gb < MIN_DISK_SPACE_GB:
        live_manager.update_log(
            event="Insufficient disk space",
            details=f"Only {free_space_gb:.2f} GB available on {root_path}. "
            "The program has been stopped to prevent data loss.",
        )
        sys.exit(1)
