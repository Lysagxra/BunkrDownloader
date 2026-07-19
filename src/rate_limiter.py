"""Thread-safe token-bucket rate limiter for capping aggregate download speed.

A single RateLimiter instance is shared across every download thread (all chunks of all
files in the current run), so --rate-limit caps the total bandwidth used by the
process -- not a per-connection or per-file limit that would be trivially multiplied by
--connections or concurrent album items.
"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """Caps aggregate throughput across every thread sharing this instance."""

    def __init__(self, rate_bytes_per_sec: float | None) -> None:
        """Initialize the limiter."""
        # rate_bytes_per_sec: Maximum aggregate bytes/sec across all callers. None or a
        # non-positive value disables throttling entirely (consume() becomes a no-op).
        self.rate = (
            rate_bytes_per_sec if rate_bytes_per_sec and rate_bytes_per_sec > 0
            else None
        )
        self._tokens = float(self.rate or 0)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    @property
    def is_limited(self) -> bool:
        """Return True if a rate cap is active."""
        return self.rate is not None

    def consume(self, n_bytes: int) -> None:
        """Block the calling thread until n_bytes of bandwidth budget is free.

        Safe to call concurrently from many threads; each call only blocks the thread
        that called it; other threads keep accumulating/spending tokens independently
        while one is sleeping.

        A single call may request more bytes than the bucket's max burst capacity
        (self.rate) -- e.g. a single large HTTP read. Tokens are allowed to go negative
        ("debt") in that case rather than requiring tokens >= n_bytes, which could never
        be satisfied since tokens are capped at self.rate; the resulting sleep duration
        below correctly repays that debt at the configured rate either way.
        """
        if self.rate is None or n_bytes <= 0:
            return

        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._last_refill = now
            self._tokens = min(self.rate, self._tokens + elapsed * self.rate)
            self._tokens -= n_bytes
            deficit = -self._tokens

        if deficit > 0:
            time.sleep(deficit / self.rate)
