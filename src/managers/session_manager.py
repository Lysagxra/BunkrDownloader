"""Configure per-session structured logs and optional diagnostic output."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src import config

if TYPE_CHECKING:
    from argparse import Namespace


def configure_session(args: Namespace) -> None:
    """Select log destinations without changing download or retry state."""
    session_id = getattr(args, "session_id", None)
    if session_id:
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", session_id)
        session_path = Path("session") / f"{safe_id}.log"
        session_path.parent.mkdir(parents=True, exist_ok=True)
        config.SESSION_LOG = str(session_path)

    event_logger = logging.getLogger("bunkr.events")
    for handler in list(event_logger.handlers):
        event_logger.removeHandler(handler)
        handler.close()

    event_logger.propagate = False
    event_logger.setLevel(logging.INFO)
    event_logger.addHandler(logging.NullHandler())

    if getattr(args, "verbose", False):
        log_dir = Path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        handler = logging.FileHandler(
            log_dir / f"verbose_{timestamp}.log", encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        event_logger.addHandler(handler)
