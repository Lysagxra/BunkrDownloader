"""Utility modules and functions to support the main application.

These utilities include functions for downloading, file management, URL handling,
progress tracking, and more.

Modules:
    - args_utils: Utilities for arguments parsing.
    - bunkr_utils: Functions for checking Bunkr status and URL validation.
    - config: Constants and settings used across the project.
    - dry_run: Preview mode: Resolve filenames and sizes without downloading.
    - file_utils: Utilities for managing file operations.
    - general_utils: Miscellaneous utility functions.
    - rate_limiter: Class for capping aggregate download speed.
    - run_utils: Utilities for processing URL batches.
    - url_utils: Utilities to analyze and extract details from URLs.

This package is designed to be reusable and modular, allowing its components
to be easily imported and used across different parts of the application.
"""

# src/__init__.py

from .version import __author__, __title__, __version__, version_info

__all__ = [
    "__author__",
    "__title__",
    "__version__",
    "args_utils",
    "bunkr_utils",
    "config",
    "dry_run",
    "file_utils",
    "general_utils",
    "rate_limiter",
    "run_utils",
    "url_utils",
    "version_info",
]
