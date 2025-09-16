"""Utility modules and functions to support the main application.

These utilities include functions for downloading, file management, URL handling,
progress tracking, and more.

Modules:
    - bunkr_utils: Functions for checking Bunkr status and URL validation.
    - config: Constants and settings used across the project.
    - file_utils: Utilities for managing file operations.
    - general_utils: Miscellaneous utility functions.
    - url_utils: Utilities to analyze and extract details from URLs.

This package is designed to be reusable and modular, allowing its components
to be easily imported and used across different parts of the application.
"""

# src/__init__.py

__all__ = [
    "bunkr_utils",
    "config",
    "file_utils",
    "general_utils",
    "url_utils",
]
