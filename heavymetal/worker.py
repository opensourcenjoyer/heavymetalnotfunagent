"""BackgroundWorker: a set of asyncio loops that restart on errors and emit alerts.

Shared by the REPL scanner (heavymetal.signals.scanner) and the Wizzy services. Subclasses implement
``loops()`` and may override ``can_start()`` to refuse starting (setting ``last_error``).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from collections.abc import Awaitable, Callable

Loop = Callable[[], Awaitable[None]]


class BackgroundWorker:
    name = "worker"
    BACKOFF_START_S = 5
    BACKOFF_MAX_S = 120

    def __init__(self, env, on_alert=None):
        self.env = env
        self.on_alert = on_alert
        self.tasks: list[asyncio.Task] = []
        self.alerts: deque = deque(maxlen=50)
        self.stats: dict[str, int] = {"errors": 0}
        self.started_at: float | None = None
        self.last_error: str | None = None

    # ------------------------------------------------------------------ to override
    def loops(self) -> tuple[Loop, ...]:
        raise NotImplementedError

    def can_start(self) -> bool:
        return True

    # ------------------------------------------------------------------ lifecycle
    @property
    def running(self) -> bool:
        return any(not t.done() for t in self.tasks)

    def start(self) -> bool:
        if self.running:
            return True
        if not self.can_start():
            return False
        self.started_at = time.time()
        self.tasks = [asyncio.create_task(self._guard(fn), name=f"{self.name}:{fn.__name__}") for fn in self.loops()]
        return True

    async def stop(self) -> None:
        for t in self.tasks:
            t.cancel()
        for t in self.tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        self.tasks = []

    async def _guard(self, fn: Loop) -> None:
        """Keep a loop alive across errors; back off on repeated failures."""
        backoff = self.BACKOFF_START_S
        while True:
            try:
                await fn()
                return
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.stats["errors"] = self.stats.get("errors", 0) + 1
                self.last_error = f"{fn.__name__}: {type(e).__name__}: {e}"[:200]
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.BACKOFF_MAX_S)

    def _alert(self, kind: str, payload: dict) -> None:
        item = {"kind": kind, "ts": time.time(), **payload}
        self.alerts.append(item)
        cb = self.on_alert
        if callable(cb):
            with contextlib.suppress(Exception):
                cb(kind, item)
