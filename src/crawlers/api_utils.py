"""Module that provides utilities for interacting with the Bunkr API.

It contains functions to:
- Request encryption-related metadata (e.g., slug resolution, encrypted URLs).
- Decrypt encrypted URLs using a time-based secret key derived from the API response.
- Handle network errors and log warnings or exceptions during API requests.
"""

from __future__ import annotations

import logging
from base64 import b64decode
from itertools import cycle
from math import floor
from typing import TYPE_CHECKING

import requests

from src.config import BUNKR_API, HEADERS, HTTPStatus
from src.url_utils import get_identifier

if TYPE_CHECKING:
    from bs4 import BeautifulSoup


def get_api_response(
    item_url: str,
    soup: BeautifulSoup | None = None,
) -> dict[str, bool | str | int] | None:
    """Fetch encryption data for a given slug from the Bunkr API."""
    slug = get_identifier(item_url, soup=soup)

    try:
        with requests.Session() as session:
            session.headers.update(HEADERS)
            response = session.post(BUNKR_API, json={"slug": slug})

            if response.status_code != HTTPStatus.OK:
                log_message = f"Failed to fetch encryption data for slug '{slug}'"
                logging.warning(log_message)
                return None

    except requests.RequestException as req_err:
        log_message = f"Error while requesting encryption data for '{slug}': {req_err}"
        logging.exception(log_message)
        return None

    return response.json()


def decrypt_url(api_response: dict[str, bool | str | int]) -> str | None:
    """Decrypt an encrypted URL using a time-based secret key."""
    try:
        timestamp = api_response["timestamp"]
        encrypted_bytes = b64decode(api_response["url"])

    except KeyError as key_err:
        log_message = f"Missing required encryption data field: {key_err}"
        logging.exception(log_message)
        return None

    # Generate the secret key based on the timestamp
    time_key = floor(timestamp / 3600)
    secret_key = f"SECRET_KEY_{time_key}"

    # Create a cyclic iterator for the secret key
    secret_key_bytes = secret_key.encode("utf-8")
    cycled_key = cycle(secret_key_bytes)

    # Decrypt the data
    decrypted_bytes = bytearray(byte ^ next(cycled_key) for byte in encrypted_bytes)
    return decrypted_bytes.decode("utf-8", errors="ignore")
