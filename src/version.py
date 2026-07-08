"""Version information for the application.

This module defines structured version metadata and exposes a unified version string
used across the application.
"""

from typing import Literal, NamedTuple


class VersionInfo(NamedTuple):
    """Structured representation of a semantic version."""

    major: int
    minor: int
    micro: int
    release_level: Literal["alpha", "beta", "final"]


version_info = VersionInfo(major=1, minor=2, micro=5, release_level="final")
is_prerelease = version_info.release_level != "final"

__author__ = "Lysagxra"
__title__ = "BunkrDownloader"
__version__ = (
    f"{version_info.major}.{version_info.minor}.{version_info.micro}"
    + (f"-{version_info.release_level}" if is_prerelease else "")
)


def get_version_string() -> str:
    """Return a formatted string representing the application version."""
    return f"{__title__} v{__version__} by {__author__}"
