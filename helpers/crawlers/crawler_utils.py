"""Module for extracting media download links from item pages."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from helpers.general_utils import fetch_page
from helpers.url_utils import (
    decrypt_url,
    get_api_response,
    get_url_based_filename,
)

if TYPE_CHECKING:
    from bs4 import BeautifulSoup


def extract_item_pages(soup: BeautifulSoup, host_page: str) -> list[str]:
    """Extract individual item page URLs from the parsed HTML content."""
    try:
        items = soup.find_all(
            "a",
            {
                "class": "after:absolute after:z-10 after:inset-0",
                "href": True,
            },
        )

        if not items:
            logging.exception("No item pages found in the HTML content.")

        return [f"{host_page}{item.get('href')}" for item in items]

    except AttributeError:
        logging.exception("Error extracting item pages.")

    return []


def get_item_container(item_soup: BeautifulSoup) -> BeautifulSoup | None:
    """Extract the first available image or source container."""
    # Try to find the <source> element
    item_container = item_soup.find("source", {"src": True})

    # If no <source> element is found, try to find an <img> element
    if item_container is None:
        item_container = item_soup.find(
            "img",
            {
                "class": "max-h-full w-auto object-cover relative z-20",
                "src": True,
            },
        )

    # Return the found element (either <source>, <img>, or None if neither was found)
    return item_container


async def get_non_media_download_link(item_soup: BeautifulSoup) -> str:
    """Extract the download link for a non-media item."""
    # Find the first download button in the initial page
    non_media_container = item_soup.find(
        "a",
        {
            "class": (
                "btn btn-main btn-lg rounded-full px-6 font-semibold flex-1 "
                "ic-download-01 ic-before before:text-lg"
            ),
            "href": True,
        },
    )

    # Fetch the page linked from the first download button
    non_media_item_soup = await fetch_page(non_media_container["href"])

    # Find the second download button in the fetched page
    non_media_download_container = non_media_item_soup.find(
        "a",
        {
            "class": (
                "btn btn-main btn-lg rounded-full px-6 font-semibold "
                "ic-download-01 ic-before before:text-lg"
            ),
            "href": True,
        },
    )

    # Return the download link extraced from the 'href' attribute
    return non_media_download_container["href"]


async def get_item_download_link(item_url: str) -> str:
    """Retrieve the download link for a specific item from its HTML content."""
    api_response = get_api_response(item_url)
    return decrypt_url(api_response)


def get_item_filename(item_soup: BeautifulSoup) -> str:
    """Extract the filename from the provided HTML soup."""
    item_filename_container = item_soup.find(
        "h1",
        {"class": "text-subs font-semibold text-base sm:text-lg truncate"},
    )
    item_filename = item_filename_container.get_text()
    return item_filename.encode("latin1").decode("utf-8")


def format_item_filename(original_filename: str, url_based_filename: str) -> str:
    """Combine two filenames while preserving the extension of the first.

    If the filenames are identical, returns the first filename.
    If the base of the first filename is found within the second, returns the second
    filename. Otherwise, combines both bases with a hyphen.
    """
    if original_filename == url_based_filename:
        return original_filename

    # Extract the base names (without extensions) and the extension
    original_base = Path(original_filename).stem
    extension = Path(original_filename).suffix
    url_base = Path(url_based_filename).stem

    if original_base in url_base:
        return url_based_filename

    # Combine the base names with a hyphen and append the extension
    return f"{original_base}-{url_base}{extension}"


async def get_download_info(item_url: str, item_soup: BeautifulSoup) -> tuple:
    """Gather download information (link and filename) for the item."""
    item_download_link = await get_item_download_link(item_url)

    item_filename = get_item_filename(item_soup)
    url_based_filename = (
        get_url_based_filename(item_download_link) if item_download_link else None
    )
    formatted_item_filename = format_item_filename(
        item_filename,
        url_based_filename,
    )

    return item_download_link, formatted_item_filename
