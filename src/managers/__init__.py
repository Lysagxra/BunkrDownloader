"""Provide modules for managing live updates within the main application.

Modules:
    - live_manager: Manages and displays live terminal updates, combining logging and
                    progress tracking.
    - log_manager: Manages the logging activities.
    - progress_manager: Manages progress tracking and reporting with tailored displays.
    - rate_limiter: Class for capping aggregate download speed.
    - session_manager: Class for session logs and diagnostic output.
    - state_manager: Manages persistent per-album crawl/download states.
    - summary_manager: Manages and presents final summaries of execution results.

This package is designed to be reusable and modular, allowing its components to be
easily imported and used across different parts of the application.
"""

# managers/__init__.py

__all__ = [
    "live_manager",
    "log_manager",
    "progress_manager",
    "rate_limiter",
    "session_manager",
    "state_manager",
    "summary_manager",
]
