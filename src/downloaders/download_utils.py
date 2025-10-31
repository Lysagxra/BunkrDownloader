"""Utilities for handling file downloads with progress tracking."""

import logging
import shutil
from pathlib import Path

from requests import Response
from requests.exceptions import ChunkedEncodingError

from src.config import LARGE_FILE_CHUNK_SIZE, THRESHOLDS
from src.managers.progress_manager import ProgressManager
from pathlib import Path
import logging


def get_chunk_size(file_size: int) -> int:
    """Determine the optimal chunk size based on the file size."""
    for threshold, chunk_size in THRESHOLDS:
        if file_size < threshold:
            return chunk_size

    # Return a default chunk size for files larger than the largest threshold
    return LARGE_FILE_CHUNK_SIZE


def save_file_with_progress(
    response: Response,
    download_path: str,
    task: int,
    progress_manager: ProgressManager,
) -> bool:
    """Save the file from the response to the specified path.

    Add a `.temp` extension if the download is partial. Handles network interruptions
    such as IncompleteRead and ConnectionResetError (wrapped in ChunkedEncodingError)
    by marking the download as incomplete.
    """
    # Determine total file size. Prefer Content-Range (when resuming) then Content-Length.
    content_range = response.headers.get("Content-Range")
    if content_range:
        # Expected format: bytes <start>-<end>/<total>
        try:
            total = int(content_range.split("/")[-1])
            file_size = total
        except Exception:
            file_size = int(response.headers.get("Content-Length", -1))
    else:
        file_size = int(response.headers.get("Content-Length", -1))

    if file_size == -1:
        logging.warning("Content length not provided in response headers.")

    # Initialize a temporary download path with the .temp extension
    download_path_obj = Path(download_path)
    temp_download_path = download_path_obj.with_suffix(".temp")

    # If a final file already exists at the target path, compare sizes and decide
    if download_path_obj.exists():
        try:
            existing_size = download_path_obj.stat().st_size
        except OSError:
            existing_size = -1

        if file_size != -1:
            if existing_size == file_size:
                logging.info(
                    "skip: %s (already exists, %d bytes)", download_path, file_size
                )
                return False
            if existing_size > file_size:
                logging.warning(
                    "conflict: %s (existing=%d bytes > expected=%d bytes)",
                    download_path,
                    existing_size,
                    file_size,
                )
                return False
            # existing_size < file_size -> resume / overwrite
            logging.info(
                "resume: %s (existing=%d bytes, expected=%d bytes)",
                download_path,
                existing_size,
                file_size,
            )
        else:
            # Unknown remote file size; if a file exists, log that we'll overwrite/continue
            logging.info(
                "resume-unknown: %s (existing file present, remote size unknown) - writing to .temp",
                download_path,
            )
    chunk_size = get_chunk_size(file_size)
    total_downloaded = 0

    # If a .temp file exists, open in append mode to resume; otherwise write new
    existing_temp_size = 0
    if temp_download_path.exists():
        try:
            existing_temp_size = temp_download_path.stat().st_size
        except OSError:
            existing_temp_size = 0

    mode = "ab" if existing_temp_size > 0 else "wb"
    total_downloaded = existing_temp_size

    try:
        with temp_download_path.open(mode) as file:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    file.write(chunk)
                    total_downloaded += len(chunk)

                    if file_size > 0:
                        completed = (total_downloaded / file_size) * 100
                    else:
                        completed = 0

                    progress_manager.update_task(task, completed=completed)

    # Handle partial downloads caused by network interruptions
    except ChunkedEncodingError:
        return True

    # Rename temp file to final filename if fully downloaded
    if file_size != -1 and total_downloaded == file_size:
        shutil.move(temp_download_path, download_path)
        return False

    # If file_size unknown, but server closed connection and we have data, consider
    # it partial (keep .temp) and return True to signal incomplete.
    if file_size == -1:
        return True

    # Keep partial file and return True if incomplete
    return True
