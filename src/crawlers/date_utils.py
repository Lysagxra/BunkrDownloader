"""Utilities for extracting and parsing item dates from Bunkr pages."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%H:%M:%S %d/%m/%Y",
)


def extract_item_dates(soup: BeautifulSoup) -> list[datetime | None]:
    """Extract item dates from an album listing page in document order.

    Each date is read from an element with the 'theDate' class and parsed from the
    'HH:MM:SS DD/MM/YYYY' format. The returned list preserves the document order so it
    can be paired positionally with the item URLs returned by extract_item_pages.
    """
    date_tags = soup.find_all(class_="theDate")
    return [_parse_date_string(tag.get_text(strip=True)) for tag in date_tags]


def get_item_date(item_soup: BeautifulSoup) -> datetime | None:
    """Extract the item's upload date from the page, if available.

    NOTE: The exact markup Bunkr uses to expose an item's date has not been confirmed
    against a live page in this environment (no network access to bunkr.* domains here).
    This tries a few common patterns, in order of reliability, and returns None (no
    mtime is set) if none match rather than guessing wrong. Once confirmed against real
    HTML, this function should be tightened to the actual selector.
    """
    # 1. Standard HTML5 <time datetime="..."> tag -- most reliable if present.
    time_tag = item_soup.find("time")
    if time_tag and time_tag.get("datetime"):
        parsed = _parse_date_string(time_tag["datetime"])
        if parsed:
            return parsed

    # 2. A tag whose visible text looks like a relative date ("... ago") and which
    #    carries the exact date in its `title` tooltip attribute -- a common pattern
    #    for these Bunkr-family frontends.
    for tag in item_soup.find_all(attrs={"title": True}):
        text = tag.get_text(strip=True)
        if re.search(r"\bago\b|\byesterday\b|\btoday\b", text, re.IGNORECASE):
            parsed = _parse_date_string(tag["title"])
            if parsed:
                return parsed

    return None


def _parse_date_string(text: str) -> datetime | None:
    """Best-effort parse of a date string into an aware UTC datetime."""
    text = text.strip()
    if not text:
        return None

    # ISO 8601, e.g. "2024-03-15T10:22:03Z" or with a numeric UTC offset.
    try:
        iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
        parsed = datetime.fromisoformat(iso_text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

    except ValueError:
        pass

    else:
        return parsed

    for date_format in _DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).replace(tzinfo=timezone.utc)

        except ValueError:
            continue

    return None
