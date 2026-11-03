"""Regression coverage for byte ranges, unknown lengths and shared service fixtures."""
import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from bs4 import BeautifulSoup
from macos.bridge import Events, run
from src.crawlers.api_utils import get_api_response
from src.crawlers.crawler_utils import extract_all_album_item_pages, get_item_filename
from src.downloaders.download_utils import _load_or_create_plan, _attempt_chunk_once, save_file_with_progress
from src.models import ChunkInfo


class IntegrityTests(unittest.TestCase):
    def test_unknown_size_and_truncated_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output"
            response = Mock(headers={})
            response.iter_content.return_value = [b"complete"]
            manager = Events(io.StringIO())
            task = manager.add_task()
            self.assertFalse(save_file_with_progress(response, str(target), task, manager))
            self.assertEqual(target.read_bytes(), b"complete")
            target.unlink()
            response.headers = {"Content-Length": "100"}
            self.assertTrue(save_file_with_progress(response, str(target), task, manager))
            self.assertFalse(target.exists())

    def test_invalid_plan_and_same_size_replacement_discard_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "media"
            plan = Path(str(target) + ".bunkrparts")
            part = Path(str(target) + ".part0")
            for ranges, validator in [([[0, 3], [3, 7]], '"old"'), ([[0, 7]], '"replaced"')]:
                plan.write_text(json.dumps({"content_length": 8, "ranges": ranges, "validator": validator}))
                part.write_bytes(b"oldbytes")
                self.assertEqual(_load_or_create_plan(target, 8, 2, '"old"'), [(0, 7)])
                self.assertFalse(part.exists())

    def test_wrong_range_never_writes_a_part(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "part"
            response = Mock(status_code=206, headers={"Content-Range": "bytes 4-7/8", "ETag": '"v1"'})
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            with patch("src.downloaders.download_utils.requests.get", return_value=response):
                self.assertTrue(_attempt_chunk_once("https://example.org", (0, 3), target,
                                                   ChunkInfo({}, Mock(), validator='"v1"', content_length=8)))
            self.assertFalse(target.exists())

    def test_shared_resolver_corpus(self):
        corpus = json.loads((Path(__file__).parents[1] / "fixtures/resolver.json").read_text())
        async def exercise():
            async def fetch(url):
                return BeautifulSoup(corpus["pages"][url], "html.parser")
            with patch("src.crawlers.crawler_utils.fetch_page", side_effect=fetch):
                items, _ = await extract_all_album_item_pages(await fetch(corpus["album"]), "https://bunkr.cr", corpus["album"])
            self.assertEqual(items, corpus["items"])
            for url, expected in zip(items, corpus["expected"]):
                soup = await fetch(url)
                async def request(_session, method, _url, **kwargs):
                    if method == "GET":
                        self.assertEqual(kwargs["params"]["path"], expected["path"])
                        return corpus["sign"]
                    return corpus["lookup"]
                with patch("src.crawlers.api_utils._request_json", side_effect=request):
                    self.assertEqual(await get_api_response(None, url, soup), expected["base"] + "?token=signed&ex=1234")
                    self.assertEqual(get_item_filename(soup), expected["name"])
            for path in ["missing", "challenge"]:
                self.assertIsNone(await get_api_response(None, "https://bunkr.cr/f/" + path, await fetch("https://bunkr.cr/f/" + path)))
        asyncio.run(exercise())

    def test_preview_does_not_create_a_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            events = Events(io.StringIO())
            with patch("src.misc.general_utils.fetch_page", AsyncMock(return_value=BeautifulSoup("<html/>", "html.parser"))), \
                 patch("downloader.resolve_album_items", AsyncMock(return_value=([], {}, {}))):
                self.assertEqual(asyncio.run(run({"url": "bunkr.cr/a/demo", "destination": directory, "preview": True}, events)), 0)
            self.assertEqual(list(Path(directory).iterdir()), [])
