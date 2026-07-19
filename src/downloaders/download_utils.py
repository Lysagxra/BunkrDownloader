"""Utilities for handling file downloads with progress tracking."""

from __future__ import annotations

import json
import logging
import random
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

import requests
from requests import Response
from requests.exceptions import ChunkedEncodingError, RequestException

from src.config import (
    CHUNK_BASE_DELAY,
    CHUNK_MAX_RETRIES,
    LARGE_FILE_CHUNK_SIZE,
    MAX_WORK_UNIT_SIZE,
    MIN_PARALLEL_SIZE,
    MIN_WORK_UNIT_SIZE,
    THRESHOLDS,
    UNITS_PER_CONNECTION,
    ChunkInfo,
    DownloadConfig,
    DownloadPlan,
)

if TYPE_CHECKING:
    from src.managers.live_manager import LiveManager
    from src.rate_limiter import RateLimiter


def get_chunk_size(file_size: int) -> int:
    """Determine the optimal chunk size based on the file size."""
    for threshold, chunk_size in THRESHOLDS:
        if file_size < threshold:
            return chunk_size

    return LARGE_FILE_CHUNK_SIZE


def save_file_with_progress(
    response: Response,
    download_path: str,
    task: int,
    live_manager: LiveManager,
    rate_limiter: RateLimiter | None = None,
) -> bool:
    """Save the file from the response to the specified path.

    Adds a `.temp` extension while downloading. Handles network interruptions
    such as IncompleteRead and ConnectionResetError (wrapped in
    ChunkedEncodingError) by marking the download as incomplete.

    Returns True on failure (partial file kept), False on success.
    """
    file_size = int(response.headers.get("Content-Length", -1))
    if file_size == -1:
        logging.warning("Content length not provided in response headers.")

    temp_download_path = Path(download_path).with_suffix(".temp")
    chunk_size = get_chunk_size(file_size)
    total_downloaded = 0

    try:
        with temp_download_path.open("wb") as file:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk is not None:
                    file.write(chunk)
                    if rate_limiter:
                        rate_limiter.consume(len(chunk))
                    total_downloaded += len(chunk)
                    completed = (total_downloaded / file_size) * 100
                    live_manager.update_task(task, completed=completed)

    except ChunkedEncodingError:
        return True

    if total_downloaded == file_size:
        shutil.move(temp_download_path, download_path)
        return False

    return True


# ==========================
# Parallel chunked download
# ==========================
def detect_range_support(
    url: str,
    headers: dict[str, str],
) -> tuple[bool, int]:
    """Send a HEAD request to detect Range support and retrieve the file size."""
    try:
        response = requests.head(url, headers=headers, timeout=10)
        response.raise_for_status()
        supports_range = response.headers.get("Accept-Ranges", "").lower() == "bytes"
        content_length = int(response.headers.get("Content-Length", -1))

    except (RequestException, ValueError):
        return False, -1

    return supports_range, content_length


def should_use_parallel_download(
    content_length: int,
    num_connections: int,
    *,
    supports_range: bool,
) -> bool:
    """Return True when conditions are met for a parallel chunked download.

    Parallel download requires:
    - Server supports byte-range requests.
    - File size is known and exceeds MIN_PARALLEL_SIZE.
    - More than one connection is requested.
    """
    return (
        supports_range and content_length >= MIN_PARALLEL_SIZE and num_connections > 1
    )


def _compute_unit_ranges(
    content_length: int,
    num_connections: int,
) -> list[tuple[int, int]]:
    """Split the file into many small work units for work-stealing download.

    The file is divided into roughly UNITS_PER_CONNECTION times more units than
    worker threads, each sized between MIN_WORK_UNIT_SIZE and MAX_WORK_UNIT_SIZE.
    Worker threads pull units from a shared queue as they finish, so a slow connection
    only delays its own next unit instead of blocking threads that finished early.

    The last unit absorbs any remainder so the entire file is always covered.
    """
    target_units = max(num_connections * UNITS_PER_CONNECTION, 1)
    raw_unit_size = content_length / target_units
    unit_size = max(
        MIN_WORK_UNIT_SIZE,
        min(int(raw_unit_size), MAX_WORK_UNIT_SIZE),
        1,
    )
    num_units = (content_length + unit_size - 1) // unit_size  # ceil division
    ranges = []

    for indx in range(num_units):
        start_byte = indx * unit_size
        end_byte = (
            (start_byte + unit_size - 1) if indx < num_units - 1 else content_length - 1
        )
        ranges.append((start_byte, end_byte))

    return ranges


def _plan_path(base_path: Path) -> Path:
    """Return the sidecar metadata path storing the chunk partition plan."""
    return Path(f"{base_path}.bunkrparts")


def _load_or_create_plan(
    base_path: Path,
    content_length: int,
    num_connections: int,
) -> list[tuple[int, int]]:
    """Load a previously persisted chunk plan, or compute and save a new one.

    Persisting the plan ensures that resuming a download after changing --connections
    (or across separate runs) reuses the exact same byte ranges. Without this, a
    stale .partN file could coincidentally match the expected size of a different
    range under a new plan and be silently merged as corrupt data.
    """
    plan_path = _plan_path(base_path)

    if plan_path.exists():
        try:
            data = json.loads(plan_path.read_text(encoding="utf-8"))
            if data.get("content_length") == content_length:
                return [tuple(pair) for pair in data["ranges"]]

        except (json.JSONDecodeError, KeyError, OSError):
            pass  # Corrupt or unreadable -- recompute below.

    ranges = _compute_unit_ranges(content_length, num_connections)

    try:
        plan_path.write_text(
            json.dumps({"content_length": content_length, "ranges": ranges}),
            encoding="utf-8",
        )

    except OSError:
        logging.warning("Could not persist chunk plan for %s", base_path)

    return ranges


def _chunk_path(base_path: Path, index: int) -> Path:
    """Return the .partN path for the given chunk index."""
    return base_path.with_suffix(f".part{index}")


def _attempt_chunk_once(
    url: str,
    byte_range: tuple[int, int],
    path: Path,
    chunk_info: ChunkInfo,
) -> bool:
    """Make a single attempt to download one byte-range chunk to disk.

    Any bytes written during a failed attempt are credited back (negative delta) via
    on_progress so the overall progress bar stays accurate when a retry re-downloads
    the same range from scratch.

    Returns:
        True on failure, False on success.

    """
    start_byte = byte_range[0]
    end_byte = byte_range[1]

    expected = end_byte - start_byte + 1
    chunk_headers = {**chunk_info.headers, "Range": f"bytes={start_byte}-{end_byte}"}
    written = 0

    try:
        with requests.get(
            url,
            headers=chunk_headers,
            stream=True,
            timeout=30,
        ) as response:
            response.raise_for_status()
            with path.open("wb") as file:
                for data in response.iter_content(chunk_size=LARGE_FILE_CHUNK_SIZE):
                    if data:
                        file.write(data)
                        num_bytes = len(data)

                        if chunk_info.rate_limiter:
                            chunk_info.rate_limiter.consume(num_bytes)

                        written += num_bytes
                        chunk_info.on_progress(num_bytes)

        if path.exists() and path.stat().st_size == expected:
            return False

    except (RequestException, OSError):
        chunk_info.on_progress(-written)
        return True

    chunk_info.on_progress(-written)
    return True


def _download_single_chunk(
    url: str,
    byte_range: tuple[int, int],
    path: Path,
    chunk_info: ChunkInfo,
) -> bool:
    """Download one byte-range chunk to disk, retrying with backoff on failure.

    Skips the download entirely when the .partN file already has the correct
    size, enabling seamless resume across sessions. Each retry re-downloads
    the chunk from scratch (the previous, incomplete attempt is overwritten).

    Returns:
        True on failure (all retries exhausted), False on success.

    """
    start_byte = byte_range[0]
    end_byte = byte_range[1]
    expected = end_byte - start_byte + 1

    # Resume: chunk already complete from a previous run, skip entirely.
    if path.exists() and path.stat().st_size == expected:
        chunk_info.on_progress(expected)
        return False

    for attempt in range(1, CHUNK_MAX_RETRIES + 1):
        failed = _attempt_chunk_once(
            url,
            (start_byte, end_byte),
            path,
            # headers,
            # on_progress,
            # rate_limiter,
            chunk_info,
        )
        if not failed:
            return False

        if attempt < CHUNK_MAX_RETRIES:
            delay = CHUNK_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1)  # noqa: S311
            time.sleep(delay)

    return True


def _build_download_plan(
    base_path: Path,
    content_length: int,
    num_connections: int,
) -> DownloadPlan:
    ranges = _load_or_create_plan(base_path, content_length, num_connections)
    num_ranges = len(ranges)
    return DownloadPlan(
        ranges=ranges,
        num_ranges=num_ranges,
        chunk_paths=[_chunk_path(base_path, indx) for indx in range(num_ranges)],
        expected_sizes=[end - start + 1 for start, end in ranges],
    )


def download_chunks(
    url: str,
    base_path: Path,
    task: int,
    live_manager: LiveManager,
    download_config: DownloadConfig,
) -> tuple[list[Path], list[int], bool]:
    """Download all work units in parallel using a thread pool.

    The file is split into more units than worker threads (see _compute_unit_ranges);
    ThreadPoolExecutor naturally hands each idle thread the next pending unit as soon as
    it finishes one, so fast connections pick up extra work instead of waiting on a slow
    one. Progress is tracked in a thread-safe manner across all workers.
    """
    lock = threading.Lock()
    total_downloaded = [0]  # mutable container for thread-safe accumulation

    def on_progress(num_bytes: int) -> None:
        with lock:
            total_downloaded[0] += num_bytes
            completed = min(
                (total_downloaded[0] / download_config.content_length) * 100,
                100.0,
            )
            live_manager.update_task(task, completed=completed)

    any_failed = False
    download_plan = _build_download_plan(
        base_path,
        download_config.content_length,
        download_config.num_connections,
    )
    max_workers = min(download_config.num_connections, download_plan.num_ranges)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _download_single_chunk,
                url,
                byte_range,
                path,
                ChunkInfo(
                    headers=download_config.headers,
                    on_progress=on_progress,
                    rate_limiter=download_config.rate_limiter,
                ),
            ): path
            for byte_range, path in zip(download_plan.ranges, download_plan.chunk_paths)
        }

        for future in as_completed(futures):
            if future.result():
                any_failed = True

    expected_sizes = [
        end_byte - start_byte + 1 for start_byte, end_byte in download_plan.ranges
    ]
    return download_plan.chunk_paths, expected_sizes, any_failed


def verify_chunks(chunk_paths: list[Path], expected_sizes: list[int]) -> bool:
    """Verify every chunk file exists and has the expected byte count."""
    return all(
        path.exists() and path.stat().st_size == size
        for path, size in zip(chunk_paths, expected_sizes)
    )


def merge_chunks(chunk_paths: list[Path], final_path: Path) -> None:
    """Concatenate ordered .partN files into the final destination file."""
    with final_path.open("wb") as destination_file:
        for chunk_path in chunk_paths:
            with chunk_path.open("rb") as chunk_file:
                shutil.copyfileobj(chunk_file, destination_file)


def cleanup(chunk_paths: list[Path], base_path: Path) -> None:
    """Remove all .partN chunk files and the plan metadata after a merge."""
    for path in [*chunk_paths, _plan_path(base_path)]:
        try:
            path.unlink(missing_ok=True)

        except OSError:
            logging.warning("Could not remove chunk file: %s", path)


def save_file_with_chunks(
    url: str,
    download_path: str,
    task: int,
    live_manager: LiveManager,
    download_config: DownloadConfig,
) -> bool:
    """Download a file using parallel byte-range chunks with resume support.

    Each chunk is saved to a dedicated .partN file so that an interrupted
    download can resume from where it left off on the next run.  Once all
    chunks are verified, they are merged into the final file and the
    temporary .partN files are removed.

    Returns:
        True on failure (.partN files kept for next resume), False on success.

    """
    base_path = Path(download_path)
    chunk_paths, expected_sizes, any_failed = download_chunks(
        url,
        base_path,
        task,
        live_manager,
        download_config,
    )

    if any_failed or not verify_chunks(chunk_paths, expected_sizes):
        # Keep .partN files so the next run can resume incomplete chunks.
        return True

    merge_chunks(chunk_paths, base_path)
    cleanup(chunk_paths, base_path)
    return False
