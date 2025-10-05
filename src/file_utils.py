"""Utilities functions for file input and output operations.

It includes methods to read the contents of a file and to write content to a file,
with optional support for clearing the file.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

from .config import (
    DOWNLOAD_FOLDER,
    MAX_FILENAME_LEN,
    SESSION_LOG,
    VALID_CHARACTERS_REGEX,
)


def read_file(filename: str) -> list[str]:
    """Read the contents of a file and returns a list of its lines."""
    with Path(filename).open(encoding="utf-8") as file:
        return file.read().splitlines()


def write_file(filename: str, content: str = "") -> None:
    """Write content to a specified file.

    If content is not provided, the file is cleared.
    """
    with Path(filename).open("w", encoding="utf-8") as file:
        file.write(content)


def write_on_session_log(content: str) -> None:
    """Append content to the session log file."""
    with Path(SESSION_LOG).open("a", encoding="utf-8") as file:
        file.write(f"{content}\n")


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
    return re.sub(VALID_CHARACTERS_REGEX, "", text)


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
