"""Module for extracting media download links from item pages."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from src.file_utils import remove_invalid_characters
from src.general_utils import fetch_page
from src.url_utils import get_url_based_filename

from .api_utils import decrypt_url, get_api_response

if TYPE_CHECKING:
    from bs4 import BeautifulSoup


def extract_next_album_pages(initial_soup: BeautifulSoup, url: str) -> list[str] | None:
    """Extract pagination links for subsequent album pages from an HTML document."""
    pagination_nav = initial_soup.find("nav", {"class": "pagination"})

    # Return None if the album consists of only one page
    if pagination_nav is None:
        return None

    pagination_text = pagination_nav.get_text()
    page_ids = re.findall(r"\d+", pagination_text)
    num_pages = max(int(page_id) for page_id in page_ids)

    # Discard the first ID since it has already been processed in the main code
    return [f"{url}?page={page}" for page in range(2, num_pages + 1)]


def extract_item_pages(soup: BeautifulSoup, host_page: str) -> list[str] | None:
    """Extract individual item page URLs from the parsed HTML content."""
    try:
        items = soup.find_all(
            "a",
            {
                "class": "after:absolute after:z-10 after:inset-0",
                "href": True,
            },
        )

        return [f"{host_page}{item.get('href')}" for item in items]

    except AttributeError:
        logging.exception("Error extracting item pages.")
        return None


async def extract_all_album_item_pages(
    initial_soup: BeautifulSoup, host_page: str, url: str,
) -> list[str]:
    """Collect item page links from an album, including pagination."""
    if initial_soup is None:
        error_message = f"Failed to parse album landing page: {url}"
        raise RuntimeError(error_message)

    # Extract item pages from the initial soup
    item_pages = extract_item_pages(initial_soup, host_page)
    if item_pages is None:
        error_message = f"Unable to extract album items from {url}"
        raise RuntimeError(error_message)

    next_album_pages = extract_next_album_pages(initial_soup, url)
    if next_album_pages is not None:
        for next_page in next_album_pages:
            next_page_soup = await fetch_page(next_page)

            if next_page_soup is None:
                error_message = f"Failed to load paginated album page: {next_page}"
                raise RuntimeError(error_message)

            next_item_pages = extract_item_pages(next_page_soup, host_page)
            item_pages.extend(next_item_pages)

    return item_pages


async def get_item_download_link(
    item_url: str,
    soup: BeautifulSoup | None = None,
) -> str:
    """Retrieve the download link for a specific item from its HTML content."""
    api_response = get_api_response(item_url, soup=soup)
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
    valid_original_base = remove_invalid_characters(original_base)
    return f"{valid_original_base}-{url_base}{extension}"


async def get_download_info(item_url: str, item_soup: BeautifulSoup) -> tuple:
    """Gather download information (link and filename) for the item."""
    item_download_link = await get_item_download_link(item_url, soup=item_soup)
    item_filename = get_item_filename(item_soup)

    url_based_filename = (
        get_url_based_filename(item_download_link) if item_download_link else None
    )
    formatted_item_filename = format_item_filename(item_filename, url_based_filename)
    return item_download_link, formatted_item_filename
