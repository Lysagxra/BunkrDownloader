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

from src.args_utils import parse_arguments
from src.config import (
    KB,
    AlbumInfo,
    DownloadInfo,
    RetryConfig,
    SessionInfo,
    SkippedReason,
    UrlInfo,
    UrlType,
)
from src.crawlers.crawler_utils import (
    extract_all_album_item_pages,
    get_download_info,
    has_cached_item_pages,
)
from src.downloaders.album_downloader import AlbumDownloader, MediaDownloader
from src.dry_run import execute_dry_run
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
    check_url_type,
    get_album_id,
    get_album_name,
    get_host_page,
    get_identifier,
    log_unavailable_url,
    normalize_url,
)

if TYPE_CHECKING:
    from argparse import Namespace

    from src.managers.live_manager import LiveManager


async def resolve_album_items(
    url_info: UrlInfo,
    download_path: str,
    identifier: str,
) -> tuple[list[str], dict]:
    """Resolve album item pages, reusing cached state when available.."""
    if url_info.is_media:
        return [url_info.url], {}

    cached_state = load_album_state(download_path)
    if has_cached_item_pages(cached_state, identifier):
        return cached_state["item_pages"], cached_state["items"]

    host_page = get_host_page(url_info.url)
    item_pages = await extract_all_album_item_pages(
        url_info.soup, host_page, url_info.url,
    )
    return item_pages, {}


async def get_item_pages_with_cache(
    url_info: UrlInfo,
    identifier: str,
    session_info: SessionInfo,
    live_manager: LiveManager,
) -> tuple[list[str], dict]:
    """Resolve album item pages and persist newly discovered state."""
    item_pages, cached_items = await resolve_album_items(
        url_info,
        session_info.download_path,
        identifier,
    )

    if cached_items:
        num_pages = len(item_pages)
        live_manager.update_log(
            event="Using cached album state",
            details=f"Reusing {num_pages} previously crawled item page(s)",
        )
        return item_pages, cached_items

    save_album_state(session_info.download_path, identifier, item_pages, {})
    return item_pages, {}


async def handle_download_process(
    url_info: UrlInfo,
    session_info: SessionInfo,
    live_manager: LiveManager,
    max_retries: int,
) -> bool:
    """Handle the download process for a Bunkr album or a single item.

    Returns:
        True if the album/item ended with a permanent failure, False otherwise.

    """
    identifier = get_identifier(url_info.url, soup=url_info.soup)

    # Album download
    if url_info.is_album:
        item_pages, cached_items = await get_item_pages_with_cache(
            url_info,
            identifier,
            session_info,
            live_manager,
        )
        album_info = AlbumInfo(album_id=identifier, item_pages=item_pages)
        album_downloader = AlbumDownloader(
            session_info=session_info,
            album_info=album_info,
            live_manager=live_manager,
            cached_items=cached_items,
        )
        return await album_downloader.download_album(max_retries=max_retries)

    # Single item download
    download_link, filename = await get_download_info(
        url_info.url,
        url_info.soup,
        clean_name=session_info.args.clean_name,
    )
    live_manager.add_overall_task(identifier, num_tasks=1)
    task = live_manager.add_task()

    media_downloader = MediaDownloader(
        session_info=session_info,
        download_info=DownloadInfo(
            item_url=url_info.url,
            download_link=download_link,
            filename=filename,
            task=task,
        ),
        live_manager=live_manager,
        retry_config = RetryConfig(),
    )
    return media_downloader.download()


async def prepare_session(
    bunkr_status: dict[str, str],
    url: str,
    args: Namespace,
    rate_limiter: RateLimiter | None = None,
) -> tuple[UrlInfo, SessionInfo] | None:
    """Fetch a URL and prepare the session required for downloading."""
    validated_url = normalize_url(url)
    soup = await fetch_page(validated_url)

    if soup is None:
        return None

    url_type = UrlType.ALBUM if check_url_type(validated_url) else UrlType.MEDIA
    url_info = UrlInfo(url=validated_url, url_type=url_type, soup=soup)

    album_id = get_album_id(validated_url) if url_info.is_album else None
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
    return url_info, session_info


async def execute_dry_run_for_url(
    bunkr_status: dict[str, str],
    url: str,
    args: Namespace,
    console: Console,
) -> None:
    """Preview an album or single-item download without downloading anything.

    Mirrors the path-resolution logic of validate_and_download/handle_download_process,
    but intentionally runs outside the Live progress UI.
    """
    prepared_session = await prepare_session(bunkr_status, url, args)
    if prepared_session is None:
        console.print(f"[red]Could not fetch {url}[/red]")
        return

    url_info, session_info = prepared_session
    identifier = get_identifier(url_info.url, soup=url_info.soup)

    item_pages, cached_items = await resolve_album_items(
        url_info, session_info.download_path, identifier,
    )
    await execute_dry_run(identifier, item_pages, session_info, cached_items, console)


async def validate_and_download(
    bunkr_status: dict[str, str],
    url: str,
    live_manager: LiveManager,
    args: Namespace,
    rate_limiter: RateLimiter | None = None,
) -> bool:
    """Validate a URL and initiate the download process.

    Returns:
        True if the URL should be kept for a future retry.
        False if the URL was successfully processed or intentionally skipped.

    """
    if not args.disable_disk_check:
        check_disk_space(live_manager, custom_path=args.custom_path)

    prepared_session = await prepare_session(bunkr_status, url, args, rate_limiter)
    if prepared_session is None:
        write_on_session_log(
            f"Request error for {url}",
            reason=SkippedReason.SERVICE_UNAVAILABLE,
        )
        log_unavailable_url(live_manager, normalize_url(url))
        return True

    url_info, session_info = prepared_session

    try:
        return await handle_download_process(
            url_info,
            session_info,
            live_manager,
            args.max_retries,
        )

    except (RequestConnectionError, Timeout, RequestException) as err:
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

    # Placeholder for integrating the Bunkr status endpoint when available
    bunkr_status: dict[str, str] = {}
    args = parse_arguments()

    if getattr(args, "dry_run", False):
        await execute_dry_run_for_url(bunkr_status, args.url, args, Console())
        return

    rate_limiter = RateLimiter(args.rate_limit * KB if args.rate_limit else None)
    live_manager = initialize_managers(disable_ui=args.disable_ui)

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
