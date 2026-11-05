"""Utility modules and functions to support the main application.

Modules:
    - config: Constants and settings used across the project.
    - enums: Enumerations defining application-wide types and status values.
    - models: Data models and runtime state containers used throughout the application.

This package is designed to be reusable and modular, allowing its components to be
easily imported and used across different parts of the application.
"""

# src/__init__.py

from .version import __author__, __title__, __version__, version_info

__all__ = [
    "__author__",
    "__title__",
    "__version__",
    "config",
    "enums",
    "models",
    "version_info",
]
