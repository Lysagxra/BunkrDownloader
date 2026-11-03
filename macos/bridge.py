"""JSON-lines adapter for the native app; stdout is exclusively protocol output."""
from __future__ import annotations

import asyncio
import contextlib
import json
import math
import os
import re
import sys
import threading
import time
from argparse import Namespace
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

# Allows direct development execution as well as the frozen engine.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import certifi

# aiohttp/OpenSSL must use the bundled trust store after moving the app.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from downloader import validate_and_download
from src.enums import CompletedReason, FailedReason, SkippedReason
from src.managers.rate_limiter import RateLimiter


class Events:
    def __init__(self, stream=None):
        self.stream = stream or sys.stdout
        self.lock = threading.RLock()
        self.tasks = {}
        self.total = 0
        self.byte_counts = {}
        self.last_progress = 0.0
        self.counts = {"completed": 0, "skipped": 0, "failed": 0}

    def emit(self, event, **values):
        with self.lock:
            self.stream.write(json.dumps({"event": event, **values}) + "\n")
            self.stream.flush()

    def add_overall_task(self, description, num_tasks):
        with self.lock:
            self.total = num_tasks
            self.emit("album", title=description, total=num_tasks)

    def add_task(self, current_task=0, total=100):
        with self.lock:
            task = len(self.tasks)
            self.tasks[task] = 0.0
            return task

    def update_task(self, task_id, completed=None, advance=0, *, visible=True):
        with self.lock:
            value = completed if completed is not None else self.tasks[task_id] + advance
            self.tasks[task_id] = min(100.0, max(0.0, value))
            now = time.monotonic()
            if now - self.last_progress >= 0.15 or value >= 100:
                self.last_progress = now
                # This is file-weighted progress, not a byte-weighted estimate.
                progress = sum(self.tasks.values()) / max(self.total, 1) / 100
                self.emit("progress", progress=min(progress, 1.0))

    def update_bytes(self, task_id, received, expected):
        with self.lock:
            self.byte_counts[task_id] = (received, expected)
            known = all(value[1] >= 0 for value in self.byte_counts.values())
            self.emit("bytes", received=sum(value[0] for value in self.byte_counts.values()),
                      expected=sum(value[1] for value in self.byte_counts.values()) if known else None)

    def update_log(self, *, event, details):
        self.emit("log", message=f"{event}: {details}")

    def update_summary(self, task_reason):
        with self.lock:
            if isinstance(task_reason, CompletedReason):
                key = "completed"
            elif isinstance(task_reason, FailedReason) or (
                isinstance(task_reason, SkippedReason)
                and task_reason in (SkippedReason.DOMAIN_OFFLINE, SkippedReason.SERVICE_UNAVAILABLE)
            ):
                key = "failed"
            else:
                key = "skipped"
            self.counts[key] += 1
            self.emit("summary", **self.counts)


def normalized_url(raw):
    raw = raw.strip()
    if "://" not in raw:
        raw = "https://" + raw
    url = urlsplit(raw)
    host = url.hostname or ""
    if (url.scheme != "https" or url.username or url.password or url.port
            or not re.fullmatch(r"(?:www\.)?bunkrr?\.[a-z]{2,}", host)
            or not re.fullmatch(r"/(?:a/[A-Za-z0-9_-]+|[fiv]/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)/?", url.path)):
        raise ValueError("Enter a Bunkr album or file link, such as https://bunkr.cr/a/albumID.")
    return urlunsplit(("https", host, url.path.rstrip("/"), "", ""))


def parse_request(request):
    url = normalized_url(request["url"])
    destination = Path(request["destination"]).expanduser()
    if not destination.is_absolute() or not destination.is_dir():
        raise ValueError("Choose an existing download folder.")
    connections = request.get("connections", 4)
    retries = request.get("retries", 5)
    rate = request.get("rateLimit", 0)
    if type(connections) is not int or not 1 <= connections <= 16:
        raise ValueError("Connections must be between 1 and 16.")
    if type(retries) is not int or not 1 <= retries <= 10:
        raise ValueError("Attempts must be between 1 and 10.")
    if type(rate) not in (int, float) or not math.isfinite(rate) or not 0 <= rate <= 1_000_000:
        raise ValueError("Invalid speed limit.")
    filters = {}
    for key in ("include", "ignore"):
        value = request.get(key, [])
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ValueError("Filename filters must be lists of text.")
        filters[key] = value
    args = Namespace(
        custom_path=str(destination), no_download_folder=True,
        no_album_folder=not request.get("albumFolders", True),
        clean_name=request.get("cleanNames", True), disable_ui=True,
        disable_disk_check=False, disable_server_check=False,
        max_retries=retries, connections=connections, rate_limit=rate,
        **filters,
    )
    return url, args


async def run(request, events):
    url, args = parse_request(request)
    if request.get("preview"):
        from downloader import resolve_album_items
        from src.misc.general_utils import fetch_page
        from src.misc.url_utils import get_album_name
        from src.misc.file_utils import format_directory_name, sanitize_directory_name
        from src.models import AlbumInfo, SessionInfo, UrlInfo
        from src.misc.url_utils import resolve_url_type
        from src.services.dry_run import resolve_preview
        soup = await fetch_page(url)
        if soup is None:
            raise ValueError("Could not fetch the preview page.")
        info = UrlInfo(url, resolve_url_type(url), soup)
        path = Path(args.custom_path)
        if not args.no_album_folder and info.is_album:
            path = path / sanitize_directory_name(format_directory_name(get_album_name(soup), urlsplit(url).path.split("/")[-1]))
        session = SessionInfo(args, {}, str(path))
        pages, cached, dates = await resolve_album_items(info, str(path), urlsplit(url).path.split("/")[-1])
        rows = await resolve_preview(AlbumInfo(url, pages, dates, cached), session)
        events.emit("preview", rows=rows)
        return 0
    events.emit("log", message="Resolving album or file…")
    failed = await validate_and_download(
        {}, url, events, args, RateLimiter(args.rate_limit * 1024 or None),
    )
    failed = failed or events.counts["failed"] > 0
    if events.total == 0:
        failed = True
        events.emit("log", message="No downloadable files were found. Check the link or retry later.")
    events.emit("result", success=not failed, **events.counts)
    return 1 if failed else 0


def main():
    events = Events()
    if "--check" in sys.argv:
        events.emit("ready", protocol=1)
        return 0
    try:
        request = json.loads(sys.stdin.readline(1_048_576))
        # Keep third-party console output away from the protocol pipe.
        with contextlib.redirect_stdout(sys.stderr):
            return asyncio.run(run(request, events))
    except (Exception, SystemExit) as error:
        events.emit("log", message=f"Download stopped: {error}")
        events.emit("result", success=False, **events.counts)
        return 1


if __name__ == "__main__":
    sys.exit(main())
