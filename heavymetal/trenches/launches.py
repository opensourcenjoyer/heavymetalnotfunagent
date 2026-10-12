"""Launch registry and the hold / ceiling ladders.

Cohort: launches up to 14 days old that traded at least signals.min_volume_h24 in 24h, at least one
day old (so the day-1 close exists). Every multiple is measured from the day-1 close, never the launch
tick. Tops are wick-proof: the highest hourly close of an hour with at least $500 traded.
The registry keeps dead launches until they age out, so the ladders are not survivor-biased.
"""

from __future__ import annotations

import time

TIERS = (2, 3, 5, 7, 10)
MAX_AGE_S = 14 * 86400
MIN_HOUR_VOL = 500
MIN_COHORT = 8


def upsert_launch(db, p: dict, source: str) -> None:
    """p: normalised GeckoTerminal pool row."""
    if not p.get("pool") or not p.get("created_ts") or time.time() - p["created_ts"] > MAX_AGE_S:
        return
    db._x(
        "INSERT INTO launches (pool, mint, symbol, created_ts, first_seen, last_price, last_ts, vol_h24, liq, source)"
        " VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(pool) DO UPDATE SET last_price=excluded.last_price,"
        " last_ts=excluded.last_ts, vol_h24=MAX(COALESCE(launches.vol_h24,0), COALESCE(excluded.vol_h24,0)),"
        " liq=excluded.liq",
        (
            p["pool"],
            p.get("mint"),
            p.get("symbol"),
            p["created_ts"],
            time.time(),
            p.get("price_usd"),
            time.time(),
            (p.get("volume") or {}).get("h24"),
            p.get("liquidity_usd"),
            source,
        ),
    )


def upsert_launch_from_pair(db, mint: str, market: dict, source: str) -> None:
    """market: the `market` block of an audit (Dexscreener pair)."""
    age_h = market.get("age_hours")
    if age_h is None or not market.get("pair"):
        return
    upsert_launch(
        db,
        {
            "pool": market["pair"],
            "mint": mint,
            "symbol": market.get("symbol"),
            "created_ts": time.time() - age_h * 3600,
            "price_usd": market.get("price_usd"),
            "volume": {"h24": market.get("volume_h24")},
            "liquidity_usd": market.get("liquidity_usd"),
        },
        source,
    )


def prune(db) -> int:
    return db._x("DELETE FROM launches WHERE created_ts < ?", (time.time() - MAX_AGE_S,)).rowcount


def d1_and_top(candles: list[dict], created_ts: float) -> tuple[float | None, float | None, float | None]:
    """From hourly candles (oldest first): (day-1 close, top close after day 1, top ts)."""
    d1_end = created_ts + 86400
    day1 = [c for c in candles if c["ts"] < d1_end]
    if not day1:
        return None, None, None
    d1_close = day1[-1]["close"]
    later = [c for c in candles if c["ts"] >= d1_end and (c["volume"] or 0) >= MIN_HOUR_VOL]
    if not later:
        return d1_close, None, None
    top = max(later, key=lambda c: c["close"])
    return d1_close, top["close"], top["ts"] + 3600


async def update_launches(env, max_ohlcv: int = 12) -> dict:
    """Fill day-1 closes from OHLCV (a few per call, to respect GeckoTerminal) and refresh live prices."""
    db = env.db
    prune(db)
    now = time.time()
    need = [
        dict(r)
        for r in db.conn.execute(
            "SELECT * FROM launches WHERE d1_close IS NULL AND created_ts < ? ORDER BY vol_h24 DESC LIMIT ?",
            (now - 86400 - 3600, max_ohlcv),
        )
    ]
    filled = 0
    for L in need:
        try:
            hours = int((now - L["created_ts"]) / 3600) + 2
            candles = await env.gecko.ohlcv(L["pool"], "hour", 1, min(hours, 1000))
        except Exception:  # noqa: BLE001
            continue
        d1, top, top_ts = d1_and_top(candles, L["created_ts"])
        if d1 is None:
            d1 = -1  # no day-1 trading recorded: never scoreable, don't refetch
        db._x(
            "UPDATE launches SET d1_close=?, top_price=MAX(COALESCE(top_price,0), COALESCE(?,0)), top_ts=COALESCE(?, top_ts),"
            " last_price=COALESCE(?, last_price) WHERE pool=?",
            (d1, top, top_ts, candles[-1]["close"] if candles else None, L["pool"]),
        )
        filled += 1
    live = [dict(r) for r in db.conn.execute("SELECT pool, mint, top_price FROM launches WHERE d1_close > 0")]
    mints = list({r["mint"] for r in live if r["mint"]})
    priced = 0
    if mints:
        try:
            pairs = await env.dex.tokens_batch(mints)
        except Exception:  # noqa: BLE001
            pairs = {}
        for r in live:
            p = pairs.get(r["mint"])
            if not p or not p.get("price_usd"):
                continue
            px = p["price_usd"]
            hour_vol = (p.get("volume") or {}).get("h1") or 0
            top = r["top_price"] or 0
            if px > top and hour_vol >= MIN_HOUR_VOL:
                db._x("UPDATE launches SET top_price=?, top_ts=? WHERE pool=?", (px, now, r["pool"]))
            db._x(
                "UPDATE launches SET last_price=?, last_ts=?, liq=? WHERE pool=?",
                (px, now, p.get("liquidity_usd"), r["pool"]),
            )
            priced += 1
    return {"d1_filled": filled, "priced": priced}


def ladders(db, min_volume: float = 25_000) -> dict:
    now = time.time()
    rows = [
        dict(r)
        for r in db.conn.execute(
            "SELECT * FROM launches WHERE d1_close > 0 AND created_ts >= ? AND created_ts <= ? AND vol_h24 >= ?",
            (now - MAX_AGE_S, now - 86400, min_volume),
        )
    ]
    n = len(rows)
    w = [t - 1 for t in TIERS]
    if not n:
        return {"cohort": 0, "hold": {}, "ceiling": {}, "hold_depth": None, "ceiling_depth": None, "thin": True}
    hold = {t: sum(1 for r in rows if (r["last_price"] or 0) / r["d1_close"] >= t) / n for t in TIERS}
    ceil = {
        t: sum(1 for r in rows if max(r["top_price"] or 0, r["last_price"] or 0) / r["d1_close"] >= t) / n
        for t in TIERS
    }
    depth = lambda d: sum(d[t] * wt for t, wt in zip(TIERS, w, strict=True)) / sum(w)  # noqa: E731
    best = sorted(rows, key=lambda r: (r["last_price"] or 0) / r["d1_close"], reverse=True)[:5]
    return {
        "cohort": n,
        "hold": {t: round(v, 4) for t, v in hold.items()},
        "ceiling": {t: round(v, 4) for t, v in ceil.items()},
        "hold_depth": round(depth(hold), 4),
        "ceiling_depth": round(depth(ceil), 4),
        "thin": n < MIN_COHORT,
        "best": [
            {
                "symbol": r["symbol"],
                "mint": r["mint"],
                "multiple": round((r["last_price"] or 0) / r["d1_close"], 2),
                "age_d": round((now - r["created_ts"]) / 86400, 1),
            }
            for r in best
        ],
    }
