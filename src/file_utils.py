"""Utilities functions for file input and output operations.

It includes methods to read the contents of a file and to write content to a file,
with optional support for clearing the file.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import importlib
from datetime import datetime
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


DEFAULT_SESSION_DIR = "session"


def get_session_log_path() -> Path:
    """Return the Path to the configured session log.

    If `SESSION_LOG` is an absolute path, use it directly. If it's just a
    filename, place it under `SESSION_DIR`. This standardizes resolution so
    callers don't need to manually recombine paths.
    """
    try:
        cfg = importlib.import_module("src.config")
        raw = getattr(cfg, "SESSION_LOG", SESSION_LOG)
        p = Path(raw)
        if p.is_absolute():
            return p
        # Treat as filename only
        return Path(DEFAULT_SESSION_DIR) / p.name
    except Exception:
        p = Path(SESSION_LOG)
        return p if p.is_absolute() else Path(DEFAULT_SESSION_DIR) / p.name


def write_on_session_log(content: str) -> None:
    """Append a URL to the session log file if not already present."""
    session_path = get_session_log_path()

    # Diagnostic: report resolved session path to verbose log (if enabled)
    write_verbose_log(f"Session log resolved to: {session_path}")

    session_path.parent.mkdir(parents=True, exist_ok=True)
    write_verbose_log(f"Ensured session directory exists: {session_path.parent}")

    # Avoid duplicate entries. Read existing lines and only append if new
    if session_path.exists():
        try:
            with session_path.open("r", encoding="utf-8") as rf:
                existing = set(line.strip() for line in rf if line.strip())
        except Exception:
            existing = set()
    else:
        existing = set()

    key = content.strip()
    if key in existing:
        write_verbose_log(f"Session log: skipped duplicate entry: {key}")
        logging.info(f"Session log skipped duplicate: {key}")
        return

    try:
        with session_path.open("a", encoding="utf-8") as file:
            file.write(f"{key}\n")
            try:
                file.flush()
                try:
                    os.fsync(file.fileno())
                except Exception:
                    pass
            except Exception:
                pass
        write_verbose_log(f"Session log: appended entry: {key}")
        logging.info(f"Session log appended: {key} -> {session_path}")
    except Exception as ex:
        write_verbose_log(f"Failed to append to session log ({session_path}): {ex}")


def is_in_session_log(content: str) -> bool:
    """Return True if the given content is already present in the session log."""
    session_path = get_session_log_path()
    try:
        if not session_path.exists():
            return False
        with session_path.open("r", encoding="utf-8") as rf:
            existing = set(line.strip() for line in rf if line.strip())
        return content.strip() in existing
    except Exception:
        return False


def set_session_log_path(session_id: str | None, download_path: str | None = None) -> None:
    """Configure the global session log path.

    Creates a unique session log filename (or one based on session_id) under
    the session directory unless SESSION_LOG is already absolute and externally
    set. Also configures verbose logging path.
    """
    try:
        cfg = importlib.import_module("src.config")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_id = sanitize_directory_name(session_id) if session_id else None

        # Decide filename (without directory) then resolve final path with helper
        if safe_id:
            filename = f"{safe_id}.txt"
        else:
            filename = f"session_{ts}.txt"

        # Store only the filename if SESSION_LOG isn't already absolute; helper will resolve.
        existing = getattr(cfg, "SESSION_LOG", None)
        if not (existing and Path(existing).is_absolute()):
            cfg.SESSION_LOG = filename

        # Ensure directory exists for resolved path
        session_path = get_session_log_path()
        session_path.parent.mkdir(parents=True, exist_ok=True)

        # Configure verbose log file
        try:
            cfg.LOG_OUTPUT_DIR = getattr(cfg, "LOG_OUTPUT_DIR", "logs")
            if safe_id:
                vfilename = f"{safe_id}_{ts}.log"
            else:
                vfilename = f"verbose_{ts}.log"
            cfg.VERBOSE_LOG = str(Path(cfg.LOG_OUTPUT_DIR) / vfilename)
            try:
                configure_logging_to_verbose()
            except Exception:
                pass
        except Exception:
            pass

        # Persist download path for retry pass reuse
        try:
            if download_path:
                cfg.SESSION_DOWNLOAD_PATH = str(download_path)
        except Exception:
            pass

        # Optionally prune older verbose logs if a named session
        try:
            if safe_id:
                logs_path = Path(cfg.LOG_OUTPUT_DIR)
                for p in logs_path.glob("verbose_*.log"):
                    try:
                        p.unlink()
                    except Exception:
                        pass
        except Exception:
            pass
    except Exception:
        pass


def set_verbose_log_path(verbose_id: str | None) -> None:
    """Configure a verbose log file path under the configured LOG_OUTPUT_DIR.

    If verbose_id is provided, file will be LOG_OUTPUT_DIR/<verbose_id>.log,
    otherwise LOG_OUTPUT_DIR/verbose.log.
    """
    try:
        cfg = importlib.import_module("src.config")
        logs_dir = Path(cfg.LOG_OUTPUT_DIR)
        logs_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{verbose_id}.log" if verbose_id else "verbose.log"
        cfg.VERBOSE_LOG = str(logs_dir / filename)
    except Exception:
        pass


def write_verbose_log(message: str) -> None:
    """Append a message to the verbose log file if configured.

    This is available at module level so callers like LiveManager and LoggerTable
    can import it directly: `from src.file_utils import write_verbose_log`.
    """
    try:
        cfg = importlib.import_module("src.config")
        verbose_path = getattr(cfg, "VERBOSE_LOG", None)
        if not verbose_path:
            return
        p = Path(verbose_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with p.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
            try:
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
            except Exception:
                pass
    except Exception:
        pass


def configure_logging_to_verbose() -> None:
    """Configure the root logger to write only to the verbose log file.

    This installs a FileHandler to `cfg.VERBOSE_LOG` and removes any
    existing StreamHandlers so console output is avoided.
    """
    try:
        cfg = importlib.import_module("src.config")
        verbose_path = getattr(cfg, "VERBOSE_LOG", None)
        if not verbose_path:
            return
        # Remove existing stream handlers
        root = logging.getLogger()
        for h in list(root.handlers):
            if isinstance(h, logging.StreamHandler):
                root.removeHandler(h)

        # Add file handler
        fh = logging.FileHandler(verbose_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(message)s"))
        fh.setLevel(logging.INFO)
        root.addHandler(fh)
        root.setLevel(logging.INFO)
    except Exception:
        pass


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


def get_session_entries_count() -> tuple[int, str]:
    """Return (count, path) for the configured session file."""
    session_path = get_session_log_path()
    try:
        if not session_path.exists():
            return 0, str(session_path)
        with session_path.open("r", encoding="utf-8") as f:
            count = sum(1 for line in f if line.strip())
        return count, str(session_path)
    except Exception:
        return 0, str(session_path)
