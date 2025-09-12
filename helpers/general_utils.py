"""Utilities for fetching pages, managing directories, and clearing the terminal.

It includes functions to handle common tasks such as sending HTTP requests,
parsing HTML, creating download directories, and clearing the terminal, making it
reusable across projects.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import sys
from http.client import RemoteDisconnected
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests import Response

from .config import (
    DOWNLOAD_FOLDER,
    DOWNLOAD_HEADERS,
    FETCH_ERROR_MESSAGES,
    MAX_FILENAME_LEN,
    HTTPStatus,
)
from .file_utils import write_on_session_log
from .url_utils import change_domain_to_cr


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
                url = change_domain_to_cr(url)
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


def format_directory_name(directory_name: str, directory_id: str | None) -> str | None:
    """Format a directory name by appending its ID in parentheses if the ID is provided.

    If the directory ID is `None`, only the directory name is returned.
    """
    if directory_name is None:
        return directory_id

    return f"{directory_name} ({directory_id})" if directory_id is not None else None


def sanitize_directory_name(directory_name: str) -> str:
    """Sanitize a given directory name by replacing invalid characters with underscores.

    Handles the invalid characters specific to Windows, macOS, and Linux.
    """
    invalid_chars_dict = {
        "nt": r'[\\/:*?"<>|]',  # Windows
        "posix": r"[/:]",       # macOS and Linux
    }
    invalid_chars = invalid_chars_dict.get(os.name)
    return re.sub(invalid_chars, "_", directory_name)


def create_download_directory(
    directory_name: str,
    custom_path: str | None = None,
) -> str:
    """Create a directory for downloads if it doesn't exist."""
    # Sanitizing the directory name (album ID), if provided
    sanitized_directory_name = (
        sanitize_directory_name(directory_name) if directory_name else None
    )

    # Determine the base download path.
    base_path = (
        Path(custom_path) / DOWNLOAD_FOLDER if custom_path else Path(DOWNLOAD_FOLDER)
    )

    # Albums containing a single file will be directly downloaded into the 'Downloads'
    # folder, without creating a subfolder for the album ID.
    download_path = (
        base_path / sanitized_directory_name if sanitized_directory_name else base_path
    )

    # Create the directory if it doesn't exist
    try:
        download_path.mkdir(parents=True, exist_ok=True)

    except OSError as os_err:
        log_message = f"Error creating 'Downloads' directory: {os_err}"
        logging.exception(log_message)
        sys.exit(1)

    return str(download_path)


def remove_invalid_characters(text: str) -> str:
    """Remove invalid characters from the input string.

    This function keeps only letters (both uppercase and lowercase), digits, spaces,
    hyphens ('-'), and underscores ('_').
    """
    return re.sub(r"[^a-zA-Z0-9 _-]", "", text)


def truncate_filename(filename: str) -> str:
    """Truncate the filename to fit within the maximum byte length."""
    filename_path = Path(filename)
    name = remove_invalid_characters(filename_path.stem)
    extension = filename_path.suffix

    if len(name) > MAX_FILENAME_LEN:
        available_len = MAX_FILENAME_LEN - len(extension)
        name = name[:available_len]

    formatted_filename = f"{name}{extension}"
    return str(filename_path.with_name(formatted_filename))


def clear_terminal() -> None:
    """Clear the terminal screen based on the operating system."""
    commands = {
        "nt": "cls",       # Windows
        "posix": "clear",  # macOS and Linux
    }

    command = commands.get(os.name)
    if command:
        os.system(command)  # noqa: S605
