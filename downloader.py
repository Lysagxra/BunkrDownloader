"""Python-based downloader for Bunkr albums and files.

Usage:
    Run the script from the command line with a valid album or media URL:
        python3 downloader.py <album_or_media_url>
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from requests.exceptions import ConnectionError as RequestConnectionError
from requests.exceptions import RequestException, Timeout

from src.bunkr_utils import get_bunkr_status
from src.config import AlbumInfo, DownloadInfo, SessionInfo, parse_arguments
from src.crawlers.crawler_utils import extract_all_album_item_pages, get_download_info
from src.downloaders.album_downloader import AlbumDownloader, MediaDownloader
from src.downloaders.retry_manager import run_session_retry_pass
from src.file_utils import (
    create_download_directory,
    format_directory_name,
    sanitize_directory_name,
    set_session_log_path,
)
from src.general_utils import (
    check_disk_space,
    check_python_version,
    clear_terminal,
    fetch_page,
)
from src.managers.live_manager import initialize_managers
from src.url_utils import (
    add_https_prefix,
    check_url_type,
    get_album_id,
    get_album_name,
    get_host_page,
    get_identifier,
    log_unavailable_url,
)

if TYPE_CHECKING:
    from argparse import Namespace

    from bs4 import BeautifulSoup

    from src.managers.live_manager import LiveManager


async def handle_download_process(
    session_info: SessionInfo,
    url: str,
    initial_soup: BeautifulSoup,
    live_manager: LiveManager,
    max_retries: int,
) -> None:
    """Handle the download process for a Bunkr album or a single item."""
    host_page = get_host_page(url)
    identifier = get_identifier(url, soup=initial_soup)
    safe_id = sanitize_directory_name(identifier) if identifier else None
    set_session_log_path(safe_id, download_path=session_info.download_path)

    # Album download
    if check_url_type(url):
        item_pages = await extract_all_album_item_pages(initial_soup, host_page, url)
        album_downloader = AlbumDownloader(
            session_info=session_info,
            album_info=AlbumInfo(album_id=identifier, item_pages=item_pages),
            live_manager=live_manager,
        )
        await album_downloader.download_album(max_retries=max_retries)

    # Single item download
    else:
        download_link, filename = await get_download_info(url, initial_soup)
        live_manager.add_overall_task(identifier, num_tasks=1)
        task = live_manager.add_task()

        media_downloader = MediaDownloader(
            session_info=session_info,
            download_info=DownloadInfo(
                download_link=download_link,
                filename=filename,
                task=task,
                display_index=1,
            ),
            live_manager=live_manager,
            retries=getattr(session_info.args, "retries", 5),
        )
        media_downloader.download()


async def validate_and_download(
    bunkr_status: dict[str, str],
    url: str,
    live_manager: LiveManager,
    args: Namespace | None = None,
) -> None:
    """Validate the provided URL, and initiate the download process."""
    # Check the available disk space on the download path before starting the download
    if not args.disable_disk_check:
        check_disk_space(live_manager, custom_path=args.custom_path)

    validated_url = add_https_prefix(url)
    soup = await fetch_page(validated_url)

    if soup is None:
        log_unavailable_url(live_manager, validated_url)
        return

    album_id = get_album_id(validated_url) if check_url_type(validated_url) else None
    album_name = get_album_name(soup)

    directory_name = format_directory_name(album_name, album_id)
    download_path = create_download_directory(
        directory_name,
        custom_path=args.custom_path,
    )
    session_info = SessionInfo(
        args=args,
        bunkr_status=bunkr_status,
        download_path=download_path,
    )

    try:
        await handle_download_process(
            session_info, validated_url, soup, live_manager, args.retries,
        )

    except (RequestConnectionError, Timeout, RequestException) as err:
        error_message = f"Error downloading from {url}: {err}"
        raise RuntimeError(error_message) from err


async def main() -> None:
    """Initialize the download process."""
    clear_terminal()
    check_python_version()

    bunkr_status = get_bunkr_status()
    args = parse_arguments()
    set_session_log_path(args.session_id)
    live_manager = initialize_managers(disable_ui=args.disable_ui, verbose=args.verbose)

    if args.disable_ui:
        try:
            cfg = importlib.import_module("src.config")
            verbose_path = getattr(cfg, "VERBOSE_LOG", "")
            print(f"Starting download (verbose log: {verbose_path})", flush=True)
        except Exception:
            print("Starting download", flush=True)

    try:
        with live_manager.live:
            await validate_and_download(
                bunkr_status,
                args.url,
                live_manager,
                args=args,
            )

            try:
                await run_session_retry_pass(live_manager)
            except Exception:
                pass

            live_manager.stop()

            # If the session log file is empty after the run, remove it
            try:
                cfg = importlib.import_module("src.config")
                session_file = Path(cfg.SESSION_LOG)
                if session_file.exists() and session_file.stat().st_size == 0:
                    session_file.unlink()
            except Exception:
                pass

    except KeyboardInterrupt:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
