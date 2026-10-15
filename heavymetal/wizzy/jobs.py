"""Durable job queue in wizzy.db, drained by a BackgroundWorker. Used for X replies, posts and owl alerts."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable

from heavymetal.worker import BackgroundWorker

MAX_ATTEMPTS = 5
Handler = Callable[[dict], Awaitable[object]]


def enqueue(wdb, kind: str, payload: dict, dedupe_key: str | None = None, run_after: float | None = None) -> int | None:
    """Add a job. Returns its id, or None if a job with the same dedupe_key already exists."""
    now = time.time()
    cur = wdb._x(
        "INSERT OR IGNORE INTO jobs(kind, payload, run_after, dedupe_key, created_at, updated_at) VALUES(?,?,?,?,?,?)",
        (kind, json.dumps(payload, default=str), run_after or now, dedupe_key, now, now),
    )
    return cur.lastrowid if cur.rowcount else None


def claim(wdb, limit: int = 5) -> list[dict]:
    now = time.time()
    rows = wdb.all("SELECT * FROM jobs WHERE status='queued' AND run_after<=? ORDER BY run_after LIMIT ?", (now, limit))
    out = []
    for r in rows:
        cur = wdb._x("UPDATE jobs SET status='running', updated_at=? WHERE id=? AND status='queued'", (now, r["id"]))
        if cur.rowcount:
            out.append(
                {"id": r["id"], "kind": r["kind"], "payload": json.loads(r["payload"]), "attempts": r["attempts"]}
            )
    return out


def done(wdb, job_id: int, result: object = None) -> None:
    wdb._x(
        "UPDATE jobs SET status='done', result=?, updated_at=? WHERE id=?",
        (json.dumps(result, default=str)[:4000], time.time(), job_id),
    )


def fail(wdb, job_id: int, attempts: int, error: str) -> None:
    attempts += 1
    if attempts >= MAX_ATTEMPTS:
        wdb._x(
            "UPDATE jobs SET status='failed', attempts=?, last_error=?, updated_at=? WHERE id=?",
            (attempts, error[:500], time.time(), job_id),
        )
        return
    delay = min(30 * 2**attempts, 3600)
    wdb._x(
        "UPDATE jobs SET status='queued', attempts=?, last_error=?, run_after=?, updated_at=? WHERE id=?",
        (attempts, error[:500], time.time() + delay, time.time(), job_id),
    )


def recover_stale(wdb, older_than_s: int = 600) -> int:
    """Jobs left 'running' by a crash go back to the queue."""
    cur = wdb._x(
        "UPDATE jobs SET status='queued' WHERE status='running' AND updated_at<?", (time.time() - older_than_s,)
    )
    return cur.rowcount


async def run_once(wdb, handlers: dict[str, Handler], limit: int = 5) -> int:
    n = 0
    for job in claim(wdb, limit):
        fn = handlers.get(job["kind"])
        if fn is None:
            fail(wdb, job["id"], MAX_ATTEMPTS, f"no handler for {job['kind']}")
            continue
        try:
            done(wdb, job["id"], await fn(job["payload"]))
            n += 1
        except Exception as e:  # noqa: BLE001
            fail(wdb, job["id"], job["attempts"], f"{type(e).__name__}: {e}")
    return n


class JobWorker(BackgroundWorker):
    name = "wizzy-jobs"

    def __init__(self, env, wdb, handlers: dict[str, Handler], interval_s: float = 2.0, on_alert=None):
        super().__init__(env, on_alert)
        self.wdb = wdb
        self.handlers = handlers
        self.interval_s = interval_s

    def loops(self):
        return (self._loop,)

    async def _loop(self) -> None:
        recover_stale(self.wdb)
        while True:
            await run_once(self.wdb, self.handlers)
            await asyncio.sleep(self.interval_s)
