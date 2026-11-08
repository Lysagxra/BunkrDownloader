"""Regression coverage for streaming resume and per-session logging."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import Mock, patch

from requests.exceptions import ChunkedEncodingError

from src import config
from src.downloaders.download_utils import save_file_with_progress
from src.downloaders.media_downloader import MediaDownloader
from src.managers.log_manager import LoggerTable
from src.managers.session_manager import configure_session
from src.misc.args_utils import parse_arguments
from src.misc.file_utils import append_suffix, write_on_session_log
from src.models import DownloadInfo, RetryConfig, SessionInfo


class ResumeTests(unittest.TestCase):
    """Exercise partial files, HTTP validation, and retry behavior offline."""

    def setUp(self) -> None:
        """Create an isolated download directory."""
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory)
        self.path = Path(self.directory) / "video.mp4"
        self.partial = append_suffix(self.path, ".temp")
        self.live = Mock()

    def response(self, status: int, body: bytes, **headers: str) -> Mock:
        """Build a streaming response with a context-manager lifecycle."""
        response = Mock(status_code=status, headers=headers)
        response.iter_content.return_value = [body]
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def save(self, response: Mock) -> bool:
        """Stream one response to the temporary destination."""
        return save_file_with_progress(response, self.path, 0, self.live)

    def test_valid_resume(self) -> None:
        """Append only the requested tail and finalize the complete file."""
        self.partial.write_bytes(b"abc")
        response = self.response(
            206,
            b"def",
            **{
                "Content-Range": "bytes 3-5/6",
                "Content-Length": "3",
            },
        )
        self.assertFalse(self.save(response))
        self.assertEqual(self.path.read_bytes(), b"abcdef")
        self.assertFalse(self.partial.exists())

    def test_ignored_range_restarts(self) -> None:
        """A full response replaces partial bytes rather than appending them."""
        self.partial.write_bytes(b"old")
        self.assertFalse(
            self.save(self.response(200, b"abcdef", **{"Content-Length": "6"}))
        )
        self.assertEqual(self.path.read_bytes(), b"abcdef")

    def test_invalid_range_preserves_partial(self) -> None:
        """Reject missing, malformed, mismatched, or incomplete range metadata."""
        for value in ("", "invalid", "bytes 0-2/6", "bytes 3-4/6", "bytes 3-8/6"):
            with self.subTest(content_range=value):
                self.partial.write_bytes(b"abc")
                response = self.response(
                    206,
                    b"def",
                    **{
                        "Content-Range": value,
                        "Content-Length": "3",
                    },
                )
                self.assertTrue(self.save(response))
                self.assertEqual(self.partial.read_bytes(), b"abc")
                self.assertFalse(self.path.exists())

    def test_invalid_lengths_and_encoding(self) -> None:
        """Reject responses that could make byte offsets unsafe."""
        for headers in (
            {"Content-Length": "bad"},
            {"Content-Length": "4", "Content-Range": "bytes 3-5/6"},
            {"Content-Range": "bytes 3-5/6", "Content-Encoding": "gzip"},
        ):
            with self.subTest(headers=headers):
                self.partial.write_bytes(b"abc")
                self.assertTrue(self.save(self.response(206, b"def", **headers)))
                self.assertEqual(self.partial.read_bytes(), b"abc")

    def test_interruption_keeps_partial(self) -> None:
        """Keep bytes written before a connection interruption for the next run."""
        response = self.response(200, b"", **{"Content-Length": "6"})

        def interrupted_stream(chunk_size: int):
            del chunk_size
            yield b"abc"
            raise ChunkedEncodingError("connection interrupted")

        response.iter_content.side_effect = interrupted_stream
        self.assertTrue(self.save(response))
        self.assertEqual(self.partial.read_bytes(), b"abc")
        self.assertFalse(self.path.exists())

    def test_short_body_remains_partial(self) -> None:
        """Never finalize a body shorter than the advertised total."""
        self.assertTrue(
            self.save(self.response(200, b"abc", **{"Content-Length": "6"}))
        )
        self.assertFalse(self.path.exists())

    def test_unknown_length(self) -> None:
        """Allow nonempty full responses without Content-Length."""
        self.assertFalse(self.save(self.response(200, b"abcdef")))
        self.assertEqual(self.path.read_bytes(), b"abcdef")

    def test_filenames_keep_extensions(self) -> None:
        """Different file extensions do not share a partial path."""
        self.assertNotEqual(
            self.partial, append_suffix(self.path.with_suffix(".jpg"), ".temp")
        )

    @patch(
        "src.downloaders.media_downloader.detect_range_support", return_value=(False, 6)
    )
    @patch("src.downloaders.media_downloader.requests.get")
    def test_download_requests_range(self, request: Mock, detect: Mock) -> None:
        """The streaming fallback requests bytes after the existing partial."""
        del detect
        self.partial.write_bytes(b"abc")
        response = self.response(
            206,
            b"def",
            **{
                "Content-Range": "bytes 3-5/6",
                "Content-Length": "3",
            },
        )
        request.return_value = response
        downloader = MediaDownloader(
            SessionInfo(Namespace(connections=1), {}, self.directory),
            DownloadInfo(
                "https://example.test/f/item",
                "https://example.test/video",
                "video.mp4",
                0,
            ),
            self.live,
            RetryConfig(retries=1),
        )
        self.assertFalse(downloader.attempt_download(self.path))
        self.assertEqual(request.call_args.kwargs["headers"]["Range"], "bytes=3-")
        response.__exit__.assert_called_once()

    def test_rejected_range_preserves_partial(self) -> None:
        """An unsatisfiable range must not be mistaken for a completed file."""
        self.partial.write_bytes(b"abc")
        self.assertTrue(self.save(self.response(416, b"")))
        self.assertEqual(self.partial.read_bytes(), b"abc")
        self.assertFalse(self.path.exists())

    @patch("src.downloaders.media_downloader.time.sleep")
    @patch(
        "src.downloaders.media_downloader.detect_range_support", return_value=(False, 6)
    )
    @patch("src.downloaders.media_downloader.requests.get")
    def test_retry_uses_saved_offset(
        self, request: Mock, detect: Mock, sleep: Mock
    ) -> None:
        """A short first response resumes during the same outer retry budget."""
        del detect, sleep
        request.side_effect = [
            self.response(200, b"abc", **{"Content-Length": "6"}),
            self.response(
                206,
                b"def",
                **{
                    "Content-Range": "bytes 3-5/6",
                    "Content-Length": "3",
                },
            ),
        ]
        downloader = MediaDownloader(
            SessionInfo(Namespace(connections=1), {}, self.directory),
            DownloadInfo(
                "https://example.test/f/item",
                "https://example.test/video",
                "video.mp4",
                0,
            ),
            self.live,
            RetryConfig(retries=2),
        )
        self.assertFalse(downloader.attempt_download(self.path))
        self.assertEqual(self.path.read_bytes(), b"abcdef")
        self.assertNotIn("Range", request.call_args_list[0].kwargs["headers"])
        self.assertEqual(
            request.call_args_list[1].kwargs["headers"]["Range"], "bytes=3-"
        )


class SessionTests(unittest.TestCase):
    """Keep log configuration compatible with current structured entries."""

    def test_named_log_and_verbose_events(self) -> None:
        """Named logs use safe paths; UI events also reach the diagnostic file."""
        original_log = config.SESSION_LOG
        self.addCleanup(setattr, config, "SESSION_LOG", original_log)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch(
                "src.managers.session_manager.Path",
                side_effect=lambda value: root / value,
            ):
                configure_session(Namespace(session_id="../album", verbose=True))
            write_on_session_log("failed item")
            self.assertEqual(Path(config.SESSION_LOG).parent, root / "session")
            self.assertIn(
                "failed item", Path(config.SESSION_LOG).read_text(encoding="utf-8")
            )
            LoggerTable().log("Retry", "Trying again")
            logs = list((root / "logs").glob("*.log"))
            self.assertEqual(len(logs), 1)
            self.assertIn("Retry | Trying again", logs[0].read_text(encoding="utf-8"))
            configure_session(Namespace(session_id=None, verbose=False))

    def test_retry_alias(self) -> None:
        """Keep old PR commands compatible with upstream's retry argument."""
        with patch("sys.argv", ["main.py", "--retries", "2"]):
            self.assertEqual(parse_arguments(common_only=True).max_retries, 2)


if __name__ == "__main__":
    unittest.main()
