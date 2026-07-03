"""Module for persisting per-album crawl/download state across runs.

For very large albums (many paginated pages, hundreds of items), re-running
the downloader would otherwise re-crawl every album listing page and
re-fetch every item page plus call the signing API even for files that were
already downloaded successfully on a previous run.

This module persists a small JSON sidecar file inside the album's download
folder so that, on a re-run for the same album:
- The paginated item-page crawl can be skipped entirely.
- Items already confirmed downloaded (and still present on disk) are
  recognized immediately, without any network round-trip.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

STATE_FILENAME = ".bunkr_state.json"


def _state_path(download_path: str) -> Path:
    """Return the sidecar state-file path for the given download folder."""
    return Path(download_path) / STATE_FILENAME


def load_album_state(download_path: str) -> dict | None:
    """Load the persisted album state for this download folder.

    Returns:
        A dict with "album_id", "item_pages" and "items" keys, or None if
        no valid state file is present (first run, or corrupt/foreign file).
    """
    path = _state_path(download_path)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logging.warning("Could not read album state file: %s", path)
        return None

    if not isinstance(data, dict) or "album_id" not in data:
        return None

    data.setdefault("item_pages", [])
    data.setdefault("items", {})
    return data


def save_album_state(
    download_path: str,
    album_id: str,
    item_pages: list[str],
    items: dict[str, dict],
) -> None:
    """Persist the full album state, overwriting any previous file."""
    path = _state_path(download_path)
    try:
        path.write_text(
            json.dumps(
                {"album_id": album_id, "item_pages": item_pages, "items": items},
            ),
            encoding="utf-8",
        )
    except OSError:
        logging.warning("Could not write album state file: %s", path)
