"""Python-based downloader for Bunkr albums and files.

Usage:
    Run the script from the command line with a valid album or media URL:
        python3 downloader.py <album_or_media_url>
"""

from __future__ import annotations

import asyncio
import sys
from argparse import ArgumentParser, Namespace
from typing import TYPE_CHECKING

from requests.exceptions import ConnectionError as RequestConnectionError
from requests.exceptions import RequestException, Timeout

from helpers.bunkr_utils import get_bunkr_status
from helpers.config import AlbumInfo, DownloadInfo, SessionInfo
from helpers.crawlers.crawler_utils import (
    extract_all_album_item_pages,
    get_download_info,
)
from helpers.downloaders.album_downloader import AlbumDownloader, MediaDownloader
from helpers.file_utils import check_disk_space, check_python_version
from helpers.general_utils import (
    clear_terminal,
    create_download_directory,
    fetch_page,
    format_directory_name,
)
from helpers.managers.live_manager import LiveManager
from helpers.managers.log_manager import LoggerTable
from helpers.managers.progress_manager import ProgressManager
from helpers.url_utils import (
    check_url_type,
    get_album_id,
    get_album_name,
    get_host_page,
    get_identifier,
)

if TYPE_CHECKING:
    from bs4 import BeautifulSoup


async def handle_download_process(
    session_info: SessionInfo,
    url: str,
    initial_soup: BeautifulSoup,
    live_manager: LiveManager,
) -> None:
    """Handle the download process for a Bunkr album or a single item."""
    host_page = get_host_page(url)
    identifier = get_identifier(url, soup=initial_soup)

    # Album download
    if check_url_type(url):
        item_pages = await extract_all_album_item_pages(initial_soup, host_page, url)
        album_downloader = AlbumDownloader(
            session_info=session_info,
            album_info=AlbumInfo(album_id=identifier, item_pages=item_pages),
            live_manager=live_manager,
        )
        await album_downloader.download_album()

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
            ),
            live_manager=live_manager,
        )
        media_downloader.download()


async def validate_and_download(
    bunkr_status: dict[str, str],
    url: str,
    live_manager: LiveManager,
    args: Namespace | None = None,
) -> None:
    """Validate the provided URL, and initiate the download process."""
    soup = await fetch_page(url)
    album_id = get_album_id(url) if check_url_type(url) else None
    album_name = get_album_name(soup)

    directory_name = format_directory_name(album_name, album_id)
    download_path = create_download_directory(
        directory_name, custom_path=args.custom_path,
    )

    # Check the available disk space on the download path before starting the download.
    check_disk_space(live_manager, custom_path=download_path)
    session_info = SessionInfo(
        args=args,
        bunkr_status=bunkr_status,
        download_path=download_path,
    )

    try:
        await handle_download_process(session_info, url, soup, live_manager)

    except (RequestConnectionError, Timeout, RequestException) as err:
        error_message = f"Error downloading from {url}: {err}"
        raise RuntimeError(error_message) from err


def initialize_managers(*, disable_ui: bool = False) -> LiveManager:
    """Initialize and return the managers for progress tracking and logging."""
    progress_manager = ProgressManager(task_name="Album", item_description="File")
    logger_table = LoggerTable()
    return LiveManager(progress_manager, logger_table, disable_ui=disable_ui)


def add_custom_path_argument(parser: ArgumentParser) -> None:
    """Add the --custom-path argument to the provided argument parser."""
    parser.add_argument(
        "--custom-path",
        type=str,
        default=None,
        help="The directory where the downloaded content will be saved.",
    )


def add_disable_ui_argument(parser: ArgumentParser) -> None:
    """Add the --disable-ui argument to any parser."""
    parser.add_argument(
        "--disable-ui",
        action="store_true",
        help="Disable the user interface",
    )


def parse_arguments() -> Namespace:
    """Parse command-line arguments."""
    parser = ArgumentParser(description="Acquire URL and other arguments.")
    parser.add_argument("url", type=str, help="The URL to process")
    parser.add_argument(
        "--ignore",
        type=str,
        nargs="+",
        help="A list of substrings to match against filenames. "
        "Files containing any of these substrings in their names will be skipped.",
    )
    parser.add_argument(
        "--include",
        type=str,
        nargs="+",
        help="A list of substrings to match against filenames. "
        "Files containing any of these substrings in their names will be downloaded.",
    )
    add_disable_ui_argument(parser)
    add_custom_path_argument(parser)
    return parser.parse_args()


async def main() -> None:
    """Initialize the download process."""
    clear_terminal()
    check_python_version()

    bunkr_status = get_bunkr_status()
    args = parse_arguments()
    live_manager = initialize_managers(disable_ui=args.disable_ui)

    try:
        with live_manager.live:
            await validate_and_download(
                bunkr_status,
                args.url,
                live_manager,
                args=args,
            )
            live_manager.stop()

    except KeyboardInterrupt:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
