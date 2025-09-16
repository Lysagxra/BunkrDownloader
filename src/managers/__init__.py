"""Provide modules for managing live updates within the main application.

It enables dynamic, real-time terminal displays and customizable progress tracking.

Modules:
    - live_manager: Manages and displays live terminal updates, combining logging and
                    progress tracking.
    - log_manager: Manages the logging activities.
    - progress_manager: Manages progress tracking and reporting with tailored displays.

This package is designed to be reusable and modular, allowing its components to be
easily imported and used across different parts of the application.
"""

# managers/__init__.py

__all__ = [
    "live_manager",
    "log_manager",
    "progress_manager",
]
