"""Module to analyze and extract details from URLs related to albums and video files.

The primary focus is on distinguishing between album URLs and individual file URLs, and
extracting relevant identifiers for albums or videos.
"""

from __future__ import annotations

import contextlib
import html
import logging
import re
import sys
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse, urlunparse

from .config import (
    FALLBACK_DOMAIN,
    MEDIA_SLUG_REGEX,
    URL_TYPE_MAPPING,
    VALID_SLUG_REGEX,
)

if TYPE_CHECKING:
    from bs4 import BeautifulSoup


def get_host_page(url: str) -> str:
    """Extract the base host URL from a given URL."""
    url_netloc = urlparse(url).netloc
    return f"https://{url_netloc}"


def add_https_prefix(url: str) -> str:
    """Add the 'https://' prefix to the provided URL if it is not already present."""
    if not url.startswith("https://"):
        return f"https://{url}"

    return url


def replace_domain_with_fallback(url: str) -> str:
    """Replace the domain of the given URL with the configured fallback domain."""
    parsed_url = urlparse(url)
    updated_url = parsed_url._replace(netloc=FALLBACK_DOMAIN)
    return urlunparse(updated_url)


def check_url_type(url: str) -> bool:
    """Determine whether the provided URL corresponds to an album or a single file."""
    try:
        url_type = url.rstrip("/").split("/")[-2]

    except IndexError:
        log_message = f"Invalid URL format for: {url}"
        logging.exception(log_message)

    if url_type in URL_TYPE_MAPPING:
        return URL_TYPE_MAPPING[url_type]

    log_message = f"Invalid URL format for: {url}. Unexpected URL type '{url_type}'."
    logging.warning(log_message)
    sys.exit(1)


def get_identifier(url: str, soup: BeautifulSoup | None = None) -> str:
    """Extract the identifier from the provided URL.

    This function determines if the given URL corresponds to an album. If it is, it
    returns the album ID. If not, it returns the last part of the URL (usually the
    individual item identifier).
    """
    decoded_url = unquote(url)

    try:
        is_album = check_url_type(decoded_url)
        return (
            get_album_id(decoded_url) if is_album else get_media_slug(decoded_url, soup)
        )

    except IndexError:
        log_message = f"Error extracting the identifier from: {url}"
        logging.exception(log_message)

    return url


def get_album_id(url: str) -> str:
    """Extract the album or video ID from the provided URL."""
    try:
        return url.rstrip("/").split("/")[-1]

    except IndexError:
        log_message = f"Invalid URL format for: {url}"
        logging.exception(log_message)
        sys.exit(1)


def get_media_slug(url: str, soup: BeautifulSoup) -> str:
    """Extract the media slug from the URL or, if necessary, from the HTML content.

    Tries to obtain the media slug (e.g., 'filename.mp4') directly from the last
    segment of the URL. If this segment is empty or unreliable, it searches the HTML
    <script> tags for a match using MEDIA_SLUG_REGEX.
    """
    # Try extracting the slug directly from the URL
    media_slug = url.rstrip("/").split("/")[-1]
    if re.fullmatch(VALID_SLUG_REGEX, media_slug):
        return media_slug

    # Fallback: try to find slug in script tags
    for item in soup.find_all("script"):
        script_text = item.get_text()
        match = re.search(MEDIA_SLUG_REGEX, script_text)
        if match:
            return match.group(1)

    return media_slug


def get_album_name(soup: BeautifulSoup) -> str | None:
    """Extract the album name from the HTML of a page.

    Handles potential mojibake issues (UTF-8 decoded as Latin-1).
    If the album name cannot be found, returns None.
    """
    name_container = soup.find(
        "div",
        {"class": "text-subs font-semibold flex text-base sm:text-lg"},
    )

    if not name_container:
        return None

    raw_album_name = name_container.find("h1").get_text(strip=True)
    unescaped_album_name = html.unescape(raw_album_name)

    # Attempt to fix mojibake (UTF-8 bytes mis-decoded as Latin-1). If encoding/decoding
    # fails, keep the decoded version
    with contextlib.suppress(UnicodeEncodeError, UnicodeDecodeError):
        fixed_album_name = unescaped_album_name.encode("latin1").decode("utf-8")

    # Only replace if the repaired string differs
    if fixed_album_name != unescaped_album_name:
        return fixed_album_name

    return unescaped_album_name


def get_item_type(item_page: str) -> str | None:
    """Extract the type of item (album or single file) from the item page URL."""
    try:
        return item_page.rstrip("/").split("/")[-2]

    except AttributeError:
        log_message = f"Error extracting the item type from {item_page}"
        logging.exception(log_message)

    return None


def get_url_based_filename(item_download_link: str) -> str:
    """Extract the filename from a download link by removing any directory structure."""
    parsed_url = urlparse(item_download_link)
    # The download link path contains the filename, preceded by a '/'
    return parsed_url.path.rstrip("/").split("/")[-1]
