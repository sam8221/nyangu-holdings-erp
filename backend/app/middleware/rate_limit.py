"""In-memory sliding-window rate limiter.

Correct for a single worker process. With several workers or servers, replace ``RateLimiter``
with a Redis-backed class exposing the same ``hit`` / ``reset`` interface.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.config import get_settings
from app.utils.exceptions import RateLimitedError


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> tuple[bool, int]:
        """Record one hit. Returns (allowed, seconds_until_retry)."""
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] >= self.window:
                bucket.popleft()
            if len(bucket) >= self.limit:
                retry_after = int(self.window - (now - bucket[0])) + 1
                return False, retry_after
            bucket.append(now)
            if len(self._hits) > 10_000:  # bound memory under key-spraying
                self._prune(now)
            return True, 0

    def _prune(self, now: float) -> None:
        for key in [k for k, b in self._hits.items() if not b or now - b[-1] >= self.window]:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_rate_limiter = RateLimiter(limit=get_settings().LOGIN_RATE_LIMIT_PER_MINUTE)


def client_ip(request: Request) -> str:
    # Behind a proxy, run uvicorn with --proxy-headers so request.client is the real client.
    return request.client.host if request.client else "unknown"


def enforce_login_rate_limit(request: Request) -> None:
    allowed, retry_after = login_rate_limiter.hit(f"login:{client_ip(request)}")
    if not allowed:
        raise RateLimitedError(
            "Too many login attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )
