"""Helper to run a single post-pass retry for URLs stored in the session file.

This module exposes an async function `run_session_retry_pass` which will:
- Read the configured session file (cfg.SESSION_LOG)
- Clear the session file so MediaDownloader won't skip retries
- For each URL in the file, attempt one download using MediaDownloader with
  retries=1. If the retry still fails, MediaDownloader will re-append the URL
  to the session file via existing logic.

The function uses the provided LiveManager to show progress/log entries during
the retry pass. If no explicit download path is available it uses the default
`Downloads` folder created by `create_download_directory`.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.url_utils import get_url_based_filename

if TYPE_CHECKING:
    from src.managers.live_manager import LiveManager


async def run_session_retry_pass(live_manager: "LiveManager") -> None:
    """Run a single retry pass over URLs listed in the session file.

    Each URL will be attempted once. If it fails again, it will be re-appended
    to the session file by existing MediaDownloader logic.
    """
    import importlib  # pylint: disable=import-outside-toplevel

    from src.file_utils import get_session_log_path  # pylint: disable=import-outside-toplevel
    session_path = get_session_log_path()

    # No session file -> nothing to do
    if not session_path.exists():
        return

    # Read all URLs
    try:
        from src.file_utils import write_verbose_log

        write_verbose_log(f"Retry pass: resolved session file: {session_path}")
        with session_path.open("r", encoding="utf-8") as rf:
            urls = [line.strip() for line in rf if line.strip()]
    except Exception:
        urls = []

    if not urls:
        write_verbose_log("Retry pass: session file contained no URLs, exiting")
        return

    write_verbose_log(f"Retry pass: read {len(urls)} URLs from session file")

    # Do NOT clear the session file here — the session file is the authoritative
    # list of deferred URLs. We'll loop over the current list and remove
    # successful URLs individually so the session file always reflects remaining
    # work.

    # Prepare a session_info-like context
    # get_bunkr_status lives in src.bunkr_utils
    from src.bunkr_utils import get_bunkr_status  # safe import here  # pylint: disable=import-outside-toplevel
    from src.config import SessionInfo  # pylint: disable=import-outside-toplevel
    from src.file_utils import create_download_directory  # pylint: disable=import-outside-toplevel

    bunkr_status = get_bunkr_status()
    default_download_path = create_download_directory(None, None)
    download_path = default_download_path
    try:
        cfg = importlib.import_module("src.config")
        download_path = getattr(cfg, "SESSION_DOWNLOAD_PATH", default_download_path)
    except Exception:
        download_path = default_download_path
    session_info = SessionInfo(args=None, bunkr_status=bunkr_status, download_path=download_path)

    # Import MediaDownloader lazily to avoid circular imports
    from src.config import DownloadInfo  # pylint: disable=import-outside-toplevel
    from src.downloaders.media_downloader import MediaDownloader  # pylint: disable=import-outside-toplevel

    try:
        live_manager.add_overall_task("Retry", num_tasks=len(urls))
        live_manager.set_post_retry_count(len(urls))
    except Exception:
        pass

    # Attempt each URL once (retries=1); remove successful URLs immediately
    # from the session file so the file always reflects remaining items.
    failed_urls: list[str] = []
    for idx, url in enumerate(urls):
        try:
            filename = get_url_based_filename(url)
        except Exception:
            filename = url.split("/")[-1] or "downloaded"

        try:
            # Create a temporary task id for UI; pass current index so the
            # per-task description shows X/N (current/total) as requested.
            try:
                # Use 1-based numbering for the retry pass so the UI shows 1/N
                # instead of 2/N offset issues observed earlier.
                task = live_manager.add_task(current_task=idx + 1, base_one=True)
            except Exception:
                task = 0

            md = MediaDownloader(
                session_info=session_info,
                # Provide a human-facing 1-based display_index for the retry pass
                # so UI messages show X/N correctly.
                download_info=DownloadInfo(
                    download_link=url,
                    filename=filename,
                    task=task,
                    display_index=idx + 1,
                ),
                live_manager=live_manager,
                retries=1,
            )
            try:
                setattr(md, "bypass_session_check", True)
            except Exception:
                pass
            # Run download synchronously in a thread
            result = await asyncio.to_thread(md.download)
            # MediaDownloader.download returns a dict on failure, None on success
            if result:
                failed_urls.append(url)
            else:
                try:
                    # Read current session contents and remove the successful URL
                    if session_path.exists():
                        with session_path.open("r", encoding="utf-8") as rf:
                            lines = [l.rstrip("\n") for l in rf if l.strip()]
                        new_lines = [l for l in lines if l.strip() != url.strip()]
                        with session_path.open("w", encoding="utf-8") as wf:
                            for l in new_lines:
                                wf.write(f"{l}\n")
                            try:
                                wf.flush()
                                import os

                                os.fsync(wf.fileno())
                            except Exception:
                                pass
                    try:
                        live_manager.increment_post_retry_count(-1)
                    except Exception:
                        pass
                    # Mark task complete in UI
                    try:
                        live_manager.update_task(task, completed=100, visible=False)
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            failed_urls.append(url)
            continue

    # After attempting all retries, write the remaining failed URLs back to
    # the session file so the user can inspect or re-run them later.
    try:
        if failed_urls:
            # Deduplicate while preserving order
            seen = set()
            uniq = [x for x in failed_urls if not (x in seen or seen.add(x))]
            session_path.parent.mkdir(parents=True, exist_ok=True)
            with session_path.open("w", encoding="utf-8") as wf:
                for u in uniq:
                    wf.write(f"{u}\n")
                try:
                    wf.flush()
                    import os

                    os.fsync(wf.fileno())
                except Exception:
                    pass
        else:
            # No failures remain; remove the session file if it exists
            try:
                session_path.unlink()
            except Exception:
                pass
    except Exception:
        pass
    finally:
        try:
            from src.file_utils import write_verbose_log

            remaining = len(failed_urls)
            removed = len(urls) - remaining
            write_verbose_log(f"Retry pass complete: {removed} removed, {remaining} remaining")
        except Exception:
            pass
