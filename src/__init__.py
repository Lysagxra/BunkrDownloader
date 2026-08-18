"""Utility modules and functions to support the main application.

Modules:
    - args_utils: Utilities for parsing command-line arguments.
    - bunkr_utils: Utilities for checking Bunkr status and validating URLs.
    - config: Constants and settings used across the project.
    - dry_run: Preview mode for resolving filenames and sizes without downloading.
    - enums: Enumerations defining application-wide types and status values.
    - file_utils: Utilities for managing file operations.
    - general_utils: Miscellaneous utility functions.
    - models: Data models and runtime state containers used throughout the application.
    - run_utils: Utilities for processing URL batches.
    - url_utils: Utilities to analyze and extract details from URLs.

This package is designed to be reusable and modular, allowing its components to be
easily imported and used across different parts of the application.
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
    "enums",
    "file_utils",
    "general_utils",
    "models",
    "run_utils",
    "url_utils",
    "version_info",
]
