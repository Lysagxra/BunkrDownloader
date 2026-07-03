"""Python-based downloader for Bunkr albums and files.

Usage:
    Run the script from the command line with a valid album or media URL:
        python3 downloader.py <album_or_media_url>
"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

from requests.exceptions import ConnectionError as RequestConnectionError
from requests.exceptions import RequestException, Timeout
from rich.console import Console

from src.bunkr_utils import get_bunkr_status
from src.config import (
    AlbumInfo,
    DownloadInfo,
    SessionInfo,
    SkippedReason,
    parse_arguments,
)
from src.crawlers.crawler_utils import (
    extract_all_album_item_pages,
    get_download_info,
)
from src.downloaders.album_downloader import AlbumDownloader, MediaDownloader
from src.dry_run import run_dry_run
from src.file_utils import (
    create_download_directory,
    format_directory_name,
    write_on_session_log,
)
from src.general_utils import (
    check_disk_space,
    check_python_version,
    clear_terminal,
    fetch_page,
)
from src.managers.live_manager import initialize_managers
from src.managers.state_manager import load_album_state, save_album_state
from src.rate_limiter import RateLimiter
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
) -> bool:
    """Handle the download process for a Bunkr album or a single item.

    Returns:
        True if the album/item ended with a permanent failure, False
        otherwise.
    """
    host_page = get_host_page(url)
    identifier = get_identifier(url, soup=initial_soup)

    # Album download
    if check_url_type(url):
        cached_state = load_album_state(session_info.download_path)

        if (
            cached_state
            and cached_state["album_id"] == identifier
            and cached_state["item_pages"]
        ):
            # Reuse the item-page list crawled on a previous run for this
            # exact album — skips fetching every paginated listing page,
            # which is the dominant cost for albums with many pages.
            item_pages = cached_state["item_pages"]
            cached_items = cached_state["items"]
            live_manager.update_log(
                event="Using cached album state",
                details=f"Reusing {len(item_pages)} previously crawled item "
                "page(s); skipping pagination crawl.",
            )
        else:
            item_pages = await extract_all_album_item_pages(
                initial_soup, host_page, url,
            )
            cached_items = {}
            save_album_state(session_info.download_path, identifier, item_pages, {})

        album_downloader = AlbumDownloader(
            session_info=session_info,
            album_info=AlbumInfo(album_id=identifier, item_pages=item_pages),
            live_manager=live_manager,
            cached_items=cached_items,
        )
        return await album_downloader.download_album(max_retries=max_retries)

    # Single item download
    download_link, filename = await get_download_info(url, initial_soup)
    live_manager.add_overall_task(identifier, num_tasks=1)
    task = live_manager.add_task()

    media_downloader = MediaDownloader(
        session_info=session_info,
        download_info=DownloadInfo(
            item_url=url,
            download_link=download_link,
            filename=filename,
            task=task,
        ),
        live_manager=live_manager,
    )
    return media_downloader.download()


async def run_dry_run_for_url(
    bunkr_status: dict[str, str],
    url: str,
    args: Namespace,
    console: Console,
) -> None:
    """Preview an album or single-item download without downloading anything.

    Mirrors the path-resolution steps of validate_and_download/
    handle_download_process, but intentionally runs outside the Live
    progress UI (nothing is being downloaded, so no progress bars are
    needed) and never constructs a MediaDownloader.
    """
    validated_url = add_https_prefix(url)
    soup = await fetch_page(validated_url)
    if soup is None:
        console.print(f"[red]Could not fetch {url}[/red]")
        return

    host_page = get_host_page(validated_url)
    identifier = get_identifier(validated_url, soup=soup)
    album_id = get_album_id(validated_url) if check_url_type(validated_url) else None
    album_name = get_album_name(soup)

    directory_name = format_directory_name(album_name, album_id)
    download_path = create_download_directory(
        directory_name,
        custom_path=args.custom_path,
        no_download_folder=args.no_download_folder,
    )
    session_info = SessionInfo(
        args=args, bunkr_status=bunkr_status, download_path=download_path,
    )

    if check_url_type(validated_url):
        cached_state = load_album_state(download_path)
        if (
            cached_state
            and cached_state["album_id"] == identifier
            and cached_state["item_pages"]
        ):
            item_pages = cached_state["item_pages"]
            cached_items = cached_state["items"]
        else:
            item_pages = await extract_all_album_item_pages(
                soup, host_page, validated_url,
            )
            cached_items = {}
    else:
        item_pages = [validated_url]
        cached_items = {}

    await run_dry_run(identifier, item_pages, session_info, cached_items, console)


async def validate_and_download(
    bunkr_status: dict[str, str],
    url: str,
    live_manager: LiveManager,
    args: Namespace | None = None,
    rate_limiter: RateLimiter | None = None,
) -> bool:
    """Validate the provided URL, and initiate the download process.

    Returns:
        True if the URL ended with a permanent failure (so the caller can
        keep it around for a retry), False if it succeeded or was skipped.
    """
    # Check the available disk space on the download path before starting the download
    if not args.disable_disk_check:
        check_disk_space(live_manager, custom_path=args.custom_path)

    validated_url = add_https_prefix(url)
    soup = await fetch_page(validated_url)

    if soup is None:
        write_on_session_log(
            f"Request error for {url}", reason=SkippedReason.SERVICE_UNAVAILABLE,
        )
        log_unavailable_url(live_manager, validated_url)
        return True

    album_id = get_album_id(validated_url) if check_url_type(validated_url) else None
    album_name = get_album_name(soup)

    directory_name = format_directory_name(album_name, album_id)
    download_path = create_download_directory(
        directory_name,
        custom_path=args.custom_path,
        no_download_folder=args.no_download_folder,
    )
    session_info = SessionInfo(
        args=args,
        bunkr_status=bunkr_status,
        download_path=download_path,
        rate_limiter=rate_limiter,
    )

    try:
        return await handle_download_process(
            session_info,
            validated_url,
            soup,
            live_manager,
            args.max_retries,
        )

    except (RequestConnectionError, Timeout, RequestException, RuntimeError) as err:
        error_message = f"Error downloading from {url}: {err}"
        write_on_session_log(
            error_message, reason=SkippedReason.SERVICE_UNAVAILABLE,
        )
        live_manager.update_log(event="Download failed", details=error_message)
        return True


async def main() -> None:
    """Initialize the download process."""
    clear_terminal()
    check_python_version()

    bunkr_status = get_bunkr_status()
    args = parse_arguments()

    if getattr(args, "dry_run", False):
        # Dry-run never downloads anything, so it runs outside the Live
        # progress UI entirely — just a one-shot table printed to a plain
        # console.
        await run_dry_run_for_url(bunkr_status, args.url, args, Console())
        return

    live_manager = initialize_managers(disable_ui=args.disable_ui)

    rate_limit_kb = getattr(args, "rate_limit", None)
    rate_limiter = RateLimiter(rate_limit_kb * 1024 if rate_limit_kb else None)

    try:
        with live_manager.live:
            await validate_and_download(
                bunkr_status,
                args.url,
                live_manager,
                args=args,
                rate_limiter=rate_limiter,
            )
            live_manager.stop()

    except KeyboardInterrupt:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
