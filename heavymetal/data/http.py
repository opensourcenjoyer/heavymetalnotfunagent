"""Shared helpers for the data connectors: a per-host rate limiter and a small TTL cache."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any


class RateLimiter:
    """At most `rate` calls per `per` seconds (sliding window). Safe to share between tasks."""

    def __init__(self, rate: int, per: float = 60.0):
        self.rate, self.per = rate, per
        self.calls: deque[float] = deque()
        self.lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self.lock:
            while True:
                now = time.monotonic()
                while self.calls and now - self.calls[0] >= self.per:
                    self.calls.popleft()
                if len(self.calls) < self.rate:
                    self.calls.append(now)
                    return
                await asyncio.sleep(self.per - (now - self.calls[0]) + 0.01)


class TTLCache:
    def __init__(self, ttl: float):
        self.ttl = ttl
        self.data: dict[Any, tuple[float, Any]] = {}

    def get(self, key):
        hit = self.data.get(key)
        if hit and time.monotonic() - hit[0] < self.ttl:
            return hit[1]
        return None

    def put(self, key, value):
        if len(self.data) > 2000:
            self.data.clear()
        self.data[key] = (time.monotonic(), value)
        return value


def fnum(v) -> float | None:
    """Parse a number that may come as a string, None or garbage."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class ConnectorError(RuntimeError):
    pass


class MissingKey(ConnectorError):
    def __init__(self, name: str):
        super().__init__(f"{name} API key not set: run /keys set {name}")
        self.name = name
