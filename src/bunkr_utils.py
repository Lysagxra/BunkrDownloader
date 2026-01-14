"""Utilities to fetch the operational status of servers from the Bunkr status page."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .config import HEADERS, STATUS_PAGE


def fetch_page(url: str) -> BeautifulSoup | None:
    """Fetch the HTML content of a page at the given URL."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()

    except requests.RequestException:
        logging.exception("An error occurred while fetching the status page.")
        return None

    return BeautifulSoup(response.text, "html.parser")


def get_bunkr_status() -> dict[str, str]:
    """Fetch the status of servers from the status page and returns a dictionary."""
    soup = fetch_page(STATUS_PAGE)
    if soup is None:
        logging.warning("Unable to fetch status page; continuing without host data.")
        return {}

    bunkr_status = {}

    try:
        server_items = soup.find_all(
            "div",
            {
                "class": (
                    "flex items-center gap-4 py-4 border-b border-soft last:border-b-0"
                ),
            },
        )

        for server_item in server_items:
            server_name = server_item.find("p").get_text(strip=True)
            server_status = server_item.find("span").get_text(strip=True)
            bunkr_status[server_name] = server_status

    except AttributeError:
        logging.exception("Error extracting server data")
        return {}

    return bunkr_status


def get_offline_servers(bunkr_status: dict[str, str] | None = None) -> dict[str, str]:
    """Return a dictionary of servers that are not operational."""
    bunkr_status = bunkr_status or get_bunkr_status()
    return {
        server_name: server_status
        for server_name, server_status in bunkr_status.items()
        if server_status != "Operational"
    }


def get_subdomain(download_link: str) -> str:
    """Extract the subdomain from a given URL."""
    netloc = urlparse(download_link).netloc
    return netloc.split(".")[0]


def subdomain_is_offline(
    download_link: str, bunkr_status: dict[str, str] | None = None,
) -> bool:
    """Check if the subdomain from the given download link is marked as offline."""
    offline_servers = get_offline_servers(bunkr_status)
    subdomain = get_subdomain(download_link)
    return subdomain in offline_servers


def mark_subdomain_as_offline(bunkr_status: dict[str, str], download_link: str) -> str:
    """Mark the subdomain of a given download link as offline in the Bunkr status."""
    subdomain = get_subdomain(download_link)
    bunkr_status[subdomain] = "Non-operational"
    return subdomain
