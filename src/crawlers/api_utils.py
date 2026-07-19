"""Utilities for resolving and signing downloadable media URLs from the Bunkr platform.

This module provides:
- Extraction of runtime variables from HTML/inline scripts
- Fallback resolution of direct download endpoints for non-landing assets
- Construction of CDN media paths
- Retrieval of signed URLs via Bunkr signing API
- Robust retry logic with exponential backoff for network resilience
"""

from __future__ import annotations

import asyncio
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse

import aiohttp

from src.config import BUNKR_API, DOWNLOAD_API, JS_VARS_COMP

if TYPE_CHECKING:
    from bs4 import BeautifulSoup


_DEFAULT_MAX_RETRIES = 5
_DEFAULT_BASE_DELAY = 2.0
_DEFAULT_TIMEOUT = 30


def unescape_js_path(value: str) -> str:
    """Normalize JavaScript-escaped URL fragments."""
    return value.replace(r"\/", "/").replace(r"\\", "\\")


def extract_page_vars(soup: BeautifulSoup) -> dict[str, str]:
    """Extract CDN/runtime variables from inline script tags."""
    for script in soup.find_all("script"):
        if script.string and "var jsCDN" in script.string:
            matches = JS_VARS_COMP.findall(script.string)
            return {
                key: unescape_js_path(value).strip("'\"")
                for key, value in matches
            }

    return {}


def extract_file_id(soup: BeautifulSoup) -> str | None:
    """Extract file identifier from HTML script metadata."""
    script = soup.find("script")
    if not script:
        return None

    return script.get("data-file-id")


async def get_download_response(
    session: aiohttp.ClientSession,
    file_id: str,
) -> str | None:
    """Fetch unsigned download URL for non-landing page assets.

    Used for file types that do not expose CDN variables (e.g. archives, videos).

    Retries with exponential backoff on network-related failures.
    Returns None instead of raising if all attempts fail, so the caller
    can skip the file gracefully without aborting the whole session.
    """
    for attempt in range(1, _DEFAULT_MAX_RETRIES + 1):
        try:
            async with session.post(
                DOWNLOAD_API,
                json={"id": file_id},
                timeout=aiohttp.ClientTimeout(total=_DEFAULT_TIMEOUT),
            ) as response:
                response.raise_for_status()
                data = await response.json()

            # Guard against unexpected API response shapes so that a schema change
            # raises a warning rather than an unhandled KeyError.
            base_url = data.get("mediafiles")
            path = data.get("path")

            if not base_url or not path:
                return None

            parsed_url = urlparse(base_url)
            return urlunparse(parsed_url._replace(path=path))

        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt < _DEFAULT_MAX_RETRIES:
                await asyncio.sleep(_DEFAULT_BASE_DELAY * (2 ** (attempt - 1)))

    return None


async def get_api_response(
    session: aiohttp.ClientSession,
    item_url: str,
    soup: BeautifulSoup | None = None,
) -> str | None:
    """Resolve and sign a Bunkr media URL using CDN or fallback pipeline.

    Resolution strategy:
        1. Extract CDN base URL from inline JavaScript (jsCDN)
        2. If missing, fallback to direct download endpoint
        3. Build media path from available source
        4. Request signed URL token from signing API

    Retries the signing API call with exponential backoff on network failures.
    Returns None if the media URL cannot be resolved or all signing attempts
    fail, allowing the caller to skip the file without crashing the session.
    """
    page_vars = extract_page_vars(soup) if soup else {}
    cdn_url = page_vars.get("jsCDN")

    # Only use the direct download endpoint when no JS vars are present,
    # which indicates an asset type without a standard landing page.
    file_id = extract_file_id(soup) if soup and not page_vars else None
    unsigned_url = await get_download_response(session, file_id) if file_id else None

    if not cdn_url and not unsigned_url:
        return None

    media_slug = PurePosixPath(urlparse(unsigned_url or item_url).path).name
    media_path = urlparse(cdn_url).path if cdn_url else f"/storage/media/{media_slug}"

    for attempt in range(1, _DEFAULT_MAX_RETRIES + 1):
        try:
            async with session.get(
                BUNKR_API,
                params={"path": media_path},
                timeout=aiohttp.ClientTimeout(total=_DEFAULT_TIMEOUT),
            ) as response:
                response.raise_for_status()
                data = await response.json()

        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt < _DEFAULT_MAX_RETRIES:
                await asyncio.sleep(_DEFAULT_BASE_DELAY * (2 ** (attempt - 1)))

        token = data.get("token")
        expires_at = data.get("ex")
        base_url = cdn_url or unsigned_url

        if token and expires_at and base_url:
            return f"{base_url}?token={token}&ex={expires_at}"

        # API responded but returned no token -> return plain CDN URL.
        return cdn_url

    return None
