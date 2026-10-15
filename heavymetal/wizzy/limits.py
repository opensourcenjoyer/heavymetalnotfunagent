"""Rate limits, per-tier quotas and kill switches. Checked before any model call."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class Verdict:
    allowed: bool
    retry_after_s: int = 0
    reason: str = ""


def hit(wdb, user_key: str, bucket: str, limit: int, window_s: int, now: float | None = None) -> Verdict:
    """Fixed-window counter in wizzy.db. Counts the attempt only when allowed."""
    now = now or time.time()
    if limit <= 0:
        return Verdict(False, window_s, f"{bucket} limit {limit}")
    row = wdb.one("SELECT window_start, count FROM rate_limits WHERE user_key=? AND bucket=?", (user_key, bucket))
    if row is None or now - row["window_start"] >= window_s:
        wdb._x(
            "INSERT INTO rate_limits(user_key, bucket, window_start, count) VALUES(?,?,?,1) "
            "ON CONFLICT(user_key, bucket) DO UPDATE SET window_start=excluded.window_start, count=1",
            (user_key, bucket, now),
        )
        return Verdict(True)
    if row["count"] >= limit:
        return Verdict(False, int(window_s - (now - row["window_start"])) + 1, f"{bucket} limit {limit}")
    wdb._x("UPDATE rate_limits SET count=count+1 WHERE user_key=? AND bucket=?", (user_key, bucket))
    return Verdict(True)


def perk(wdb, user_id: int, flag: str) -> float:
    """A familiar's perk, active only while the user is in the Inner Circle."""
    if wdb.tier(user_id) != "inner":
        return 0.0
    row = wdb.one("SELECT value FROM perks WHERE user_id=? AND flag=?", (user_id, flag))
    return float(row["value"]) if row else 0.0


def reading_quota(ctx, user_id: int) -> int:
    w = ctx.wcfg
    base = w.inner_readings_per_hour if ctx.wdb.tier(user_id) == "inner" else w.free_readings_per_hour
    return base + int(perk(ctx.wdb, user_id, "extra_readings_hour"))


def check_reading(ctx, user_id: int, surface: str) -> Verdict:
    """Per-user hourly reading quota plus a per-surface flood guard."""
    w = ctx.wcfg
    if not w.enabled:
        return Verdict(False, 0, "Wizzy is resting")
    if (surface == "tg" and not w.tg_enabled) or (surface == "x" and not w.x_enabled):
        return Verdict(False, 0, f"{surface} is paused")
    v = hit(ctx.wdb, f"u{user_id}", "reading_hour", reading_quota(ctx, user_id), 3600)
    if not v.allowed:
        return v
    return hit(ctx.wdb, "global", f"{surface}_minute", 60, 60)


def check_chat(ctx, chat_key: str, per_minute: int = 20) -> Verdict:
    """Flood guard for any message in a chat, applied before routing (and before any model call)."""
    return hit(ctx.wdb, chat_key, "chat_minute", per_minute, 60)
