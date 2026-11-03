"""Offline integration tests for the native adapter and safe file publication."""
import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bs4 import BeautifulSoup

from macos.bridge import Events, normalized_url, parse_request, run
from src.downloaders.download_utils import merge_chunks
from src.enums import CompletedReason, SkippedReason


class BridgeTests(unittest.TestCase):
    def test_url_validation_and_normalization(self):
        self.assertEqual(normalized_url("bunkr.cr/f/archive-001.tar.gz"), "https://bunkr.cr/f/archive-001.tar.gz")
        self.assertEqual(normalized_url("bunkr.si/a/abc/?page=2"), "https://bunkr.si/a/abc")
        for url in ["file:///tmp/a", "https://bunkr.cr.evil.com/a/x", "https://bunkr.cr/a/..", "https://user@bunkr.cr/f/x", "http://bunkr.cr/f/x", "https://bunkr.cr:99/f/x"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalized_url(url)

    def test_invalid_numeric_options(self):
        with tempfile.TemporaryDirectory() as directory:
            request = {"url": "bunkr.cr/f/test", "destination": directory}
            for key, value in [("connections", 0), ("connections", True), ("retries", -1), ("rateLimit", float("nan"))]:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    parse_request({**request, key: value})

    def test_real_single_file_pipeline_with_fixture_response(self):
        class Response:
            headers = {"Content-Length": "12"}
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def raise_for_status(self): pass
            def iter_content(self, chunk_size): yield b"hello bunkr!"
        with tempfile.TemporaryDirectory() as directory:
            events = Events(io.StringIO())
            request = {"url": "bunkr.cr/f/example", "destination": directory, "retries": 2}
            with patch("downloader.fetch_page", AsyncMock(return_value=BeautifulSoup("<html/>", "html.parser"))), \
                 patch("downloader.get_download_info", AsyncMock(return_value=("https://cdn.example/test", "fixture.txt", None))), \
                 patch("src.downloaders.media_downloader.detect_range_support", return_value=(False, 12)), \
                 patch("src.downloaders.media_downloader.requests.get", return_value=Response()):
                self.assertEqual(asyncio.run(run(request, events)), 0)
            self.assertEqual((Path(directory) / "fixture.txt").read_bytes(), b"hello bunkr!")
            records = [json.loads(line) for line in events.stream.getvalue().splitlines()]
            self.assertTrue(records[-1]["success"])
            self.assertEqual(records[-1]["completed"], 1)

    def test_fetch_failure_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            events = Events(io.StringIO())
            with patch("downloader.fetch_page", AsyncMock(return_value=None)), patch("downloader.write_on_session_log"):
                code = asyncio.run(run({"url": "bunkr.cr/f/test", "destination": directory}, events))
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(events.stream.getvalue().splitlines()[-1])["success"])

    def test_progress_retries_and_skips_do_not_double_count(self):
        events = Events(io.StringIO())
        events.add_overall_task("test", 2)
        task = events.add_task()
        events.update_task(task, completed=100)
        events.update_task(task, completed=100)
        self.assertEqual(json.loads(events.stream.getvalue().splitlines()[-1])["progress"], 0.5)
        events.update_summary(CompletedReason.DOWNLOAD_SUCCESS)
        events.update_summary(SkippedReason.ALREADY_DOWNLOADED)
        self.assertEqual(events.counts, {"completed": 1, "failed": 0, "skipped": 1})
        events.update_summary(SkippedReason.DOMAIN_OFFLINE)
        self.assertEqual(events.counts["failed"], 1)

    def test_interrupted_merge_never_publishes_partial_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chunk = root / "chunk"
            chunk.write_bytes(b"first")
            destination = root / "final"
            with self.assertRaises(FileNotFoundError):
                merge_chunks([chunk, root / "missing"], destination)
            self.assertFalse(destination.exists())
            merge_chunks([chunk], destination)
            self.assertEqual(destination.read_bytes(), b"first")
            self.assertFalse((root / "final.merging").exists())


if __name__ == "__main__":
    unittest.main()
