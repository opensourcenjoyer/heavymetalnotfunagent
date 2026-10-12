"""Trench Pulse: Solana smallcap volume, read live and banked daily.

Definitions
- Smallcap volume: every DEX pool except pairs whose both sides are majors/stables, tokens above $200M FDV,
  tokenized equities, and wash/inorganic/farm pools (see gates.py). Every drop is counted with its dollars.
- Trench 24H: smallcap minus the day's top-5 tickers (same-ticker pools are one ticker).
- Pace: 6h volume x4 vs 24h.
Sources (versioned, never silently joined): `dune` = every trade of the last complete UTC day (needs a key),
`gt` = GeckoTerminal's 200 most-traded pools (rolling 24h), `est` = DefiLlama chain volume x the measured
smallcap share (history before the ledger, and days the app was not running).
"""

from __future__ import annotations

import datetime as dt
import json
import statistics
import time

from heavymetal.signals.farm import classify_farm, metrics_from
from heavymetal.trenches import fear_greed
from heavymetal.trenches.gates import MAJOR_MINTS, gate_pool, is_equity, ticker_key
from heavymetal.trenches.launches import ladders, update_launches, upsert_launch

VOLUME_DEF_VERSION = 1
CACHE_S = 600
_cache: dict = {}


def today() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")


def _agg(kept: list[tuple[dict, float, float]], drops: dict, total: float, n: int, source: str) -> dict:
    """kept: (row, vol24, vol6)."""
    smallcap = sum(v for _, v, _ in kept)
    tick: dict[str, float] = {}
    for r, v, _ in kept:
        tick[ticker_key(r)] = tick.get(ticker_key(r), 0) + v
    top = sorted(tick.items(), key=lambda kv: -kv[1])[:5]
    top_vol = sum(v for _, v in top)
    v6 = sum(x for _, _, x in kept if x is not None)
    return {
        "source": source,
        "smallcap_vol": round(smallcap, 2),
        "trench_vol": round(smallcap - top_vol, 2),
        "total_vol": round(total, 2),
        "top5_share": round(top_vol / smallcap, 4) if smallcap else None,
        "top5": [
            {"symbol": k, "vol": round(v, 2), "share": round(v / smallcap, 4) if smallcap else None} for k, v in top
        ],
        "pace": round(v6 * 4 / smallcap, 3) if smallcap and v6 else None,
        "pools": n,
        "kept": len(kept),
        "drops": drops,
    }


async def sweep(env) -> tuple[dict, list[dict]]:
    """GeckoTerminal top-200 sweep through the gates. Returns (aggregate, raw pools)."""
    pools = await env.gecko.top_pools(pages=10)
    kept, drops, total = [], {}, 0.0
    for p in pools:
        v = (p.get("volume") or {}).get("h24") or 0
        total += v
        why, _ = gate_pool(p, env.cfg)
        if why:
            d = drops.setdefault(why, {"n": 0, "vol": 0.0})
            d["n"] += 1
            d["vol"] = round(d["vol"] + v, 2)
            continue
        kept.append((p, v, (p.get("volume") or {}).get("h6")))
    return _agg(kept, drops, total, len(pools), "gt"), pools


async def dune_day(env, pools_by_mint: dict[str, dict]) -> dict | None:
    """Full-population smallcap volume for the last complete UTC day, from the user's saved Dune query."""
    k = env.cfg.keys
    if not (k.dune and k.dune_query_id and getattr(env, "dune", None)):
        return None
    res = await env.dune.latest_results(k.dune_query_id)
    rows = res["rows"]
    if not rows:
        return None
    day = str(rows[0].get("day") or "")[:10] or None
    kept, drops, total = [], {}, 0.0
    cap = env.cfg.signals.smallcap_fdv_cap
    for r in rows:
        v = float(r.get("volume_usd") or 0)
        total += v
        mint = r.get("mint")
        gt = pools_by_mint.get(mint)
        why = None
        if mint in MAJOR_MINTS:
            why = "major"
        elif gt and (gt.get("fdv") or 0) > cap:
            why = "megacap"
        elif gt and is_equity(gt.get("symbol"), gt.get("price_usd")):
            why = "equity"
        else:
            farm = classify_farm(
                metrics_from(
                    gt=gt,
                    dune={
                        "mint": mint,
                        "symbol": r.get("symbol"),
                        "volume_usd": v,
                        "swaps": r.get("swaps"),
                        "traders": r.get("traders"),
                        "min_fee_tier": r.get("min_fee_tier"),
                    },
                ),
                env.cfg,
            )
            why = farm.kind if farm.is_farm else None
        if why:
            d = drops.setdefault(why, {"n": 0, "vol": 0.0})
            d["n"] += 1
            d["vol"] = round(d["vol"] + v, 2)
        else:
            kept.append(({"symbol": r.get("symbol"), "mint": mint}, v, None))
    agg = _agg(kept, drops, total, len(rows), "dune")
    agg.update(day=day, complete=res["complete"], rows_read=len(rows), rows_total=res["total"])
    return agg


def bank(db, day: str, agg: dict, chain_total: float | None) -> None:
    """Write one day. Never overwrite a dune day with a sweep, nor any measured day with an estimate."""
    cur = db.conn.execute("SELECT source FROM trench_days WHERE day=?", (day,)).fetchone()
    rank = {"est": 0, "gt": 1, "dune": 2}
    if cur and rank.get(cur["source"], 0) > rank.get(agg["source"], 0):
        return
    db._x(
        "INSERT OR REPLACE INTO trench_days (day, source, smallcap_vol, trench_vol, total_vol, top5_share, pools,"
        " drops, top, pace, chain_total, version, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            day,
            agg["source"],
            agg["smallcap_vol"],
            agg.get("trench_vol"),
            agg.get("total_vol"),
            agg.get("top5_share"),
            agg.get("pools"),
            json.dumps(agg.get("drops") or {}),
            json.dumps(agg.get("top5") or []),
            agg.get("pace"),
            chain_total,
            VOLUME_DEF_VERSION,
            time.time(),
        ),
    )


def backfill_estimates(db, llama_days: list[tuple[str, float]], max_days: int = 400) -> int:
    """Fill days with no measurement: DefiLlama chain volume x the median measured smallcap share."""
    measured = [
        dict(r)
        for r in db.conn.execute(
            "SELECT day, smallcap_vol, chain_total FROM trench_days WHERE source IN ('gt','dune') AND chain_total > 0"
        )
    ]
    shares = [r["smallcap_vol"] / r["chain_total"] for r in measured if r["smallcap_vol"]]
    if not shares:
        return 0
    share = statistics.median(shares)
    have = {r["day"]: r["source"] for r in db.conn.execute("SELECT day, source FROM trench_days")}
    n = 0
    for day, vol in llama_days[-max_days:]:
        if have.get(day) in ("gt", "dune") or day == today():
            continue
        db._x(
            "INSERT OR REPLACE INTO trench_days (day, source, smallcap_vol, chain_total, version, updated_at)"
            " VALUES (?,?,?,?,?,?)",
            (day, "est", round(vol * share, 2), vol, VOLUME_DEF_VERSION, time.time()),
        )
        n += 1
    return n


def series(db, days: int = 400, include_today: bool = True) -> list[dict]:
    rows = [
        {
            "day": r["day"],
            "smallcap": r["smallcap_vol"],
            "source": r["source"],
            "version": r["version"],
            "trench": r["trench_vol"],
            "top5_share": r["top5_share"],
        }
        for r in db.conn.execute("SELECT * FROM trench_days ORDER BY day DESC LIMIT ?", (days + 1,))
    ][::-1]
    if not include_today:
        rows = [r for r in rows if r["day"] != today()]
    return rows


def ema(vals: list[float], n: int) -> float | None:
    if not vals:
        return None
    k, e = 2 / (n + 1), vals[0]
    for v in vals[1:]:
        e = v * k + e * (1 - k)
    return e


def regime(vals: list[float]) -> dict:
    if len(vals) < 10:
        return {"label": "n/a"}
    x = vals[-1]
    out = {}
    for w in (90, 180, 365):
        hist = vals[-w:]
        out[str(w)] = round(100 * sum(1 for v in hist if v <= x) / len(hist)) if len(hist) >= 10 else None
    p = out.get("90")
    out["label"] = (
        "n/a"
        if p is None
        else "hot"
        if p >= 80
        else "warming"
        if p >= 60
        else "normal"
        if p >= 40
        else "cooling"
        if p >= 20
        else "cold"
    )
    return out


def _pct(a, b):
    return round(100 * (a / b - 1), 1) if a and b else None


_locks: dict = {}


async def refresh(env, force: bool = False) -> dict:
    """Sweep, bank, backfill, update launches, score Fear & Greed. Cached for CACHE_S; one refresh at a time."""
    import asyncio

    key = id(env.db)
    lock = _locks.setdefault((key, id(asyncio.get_running_loop())), asyncio.Lock())
    async with lock:
        hit = _cache.get(key)
        if hit and not force and time.time() - hit["_t"] < CACHE_S:
            return hit["data"]
        return await _refresh(env, key)


async def _refresh(env, key) -> dict:
    db = env.db
    notes: list[str] = []
    agg, pools = await sweep(env)
    s = env.cfg.signals
    for p in pools:  # launches <= 14 days old in the sweep join the cohort
        if (p.get("age_hours") or 1e9) <= 14 * 24 and ((p.get("volume") or {}).get("h24") or 0) >= s.min_volume_h24:
            why, _ = gate_pool(p, env.cfg)
            if not why:
                upsert_launch(db, p, source="sweep")
    llama = None
    try:
        llama = await env.llama.chain_dex_volume("solana")
    except Exception as e:  # noqa: BLE001
        notes.append(f"defillama unavailable: {e}"[:120])
    chain_total = (llama or {}).get("total24h")
    agg["coverage"] = round(agg["smallcap_vol"] / chain_total, 3) if chain_total else None
    bank(db, today(), agg, chain_total)
    dune = None
    try:
        dune = await dune_day(env, {p["mint"]: p for p in pools if p.get("mint")})
        if dune and dune.get("day"):
            ct = next((v for d, v in (llama or {}).get("days", []) if d == dune["day"]), None)
            bank(db, dune["day"], dune, ct)
            if not dune.get("complete"):
                notes.append(f"dune read {dune['rows_read']} of {dune['rows_total']} rows: partial population")
    except Exception as e:  # noqa: BLE001
        notes.append(f"dune: {e}"[:160])
    if llama:
        backfill_estimates(db, llama["days"])
    try:
        await update_launches(env)
    except Exception as e:  # noqa: BLE001
        notes.append(f"launch update: {e}"[:120])
    lad = ladders(db, s.min_volume_h24)
    ser = series(db)
    hist = [dict(r) for r in db.conn.execute("SELECT * FROM fg_days ORDER BY day DESC LIMIT 3")][::-1]
    hold_hist = [h["hold_depth"] for h in hist if h["day"] != today()]
    fg = fear_greed.compute(env.cfg, ser, lad, hold_hist)
    db._x(
        "INSERT OR REPLACE INTO fg_days (day, idx, volume, momentum, hold, ceiling, cohort, hold_depth, ceiling_depth,"
        " updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            today(),
            fg["index"],
            fg["arms"]["volume"],
            fg["arms"]["momentum"],
            fg["arms"]["hold"],
            fg["arms"]["ceiling"],
            lad["cohort"],
            lad["hold_depth"],
            lad["ceiling_depth"],
            time.time(),
        ),
    )
    vals = [r["smallcap"] for r in ser if r["smallcap"]]
    full = [r for r in ser if r["day"] != today() and r["smallcap"]]
    fg_hist = [dict(r) for r in db.conn.execute("SELECT day, idx FROM fg_days ORDER BY day DESC LIMIT 30")][::-1]
    data = {
        "as_of": time.time(),
        "today": agg,
        "dune": dune,
        "chain_total": chain_total,
        "series": ser[-120:],
        "ema7": ema(vals, 7),
        "ema14": ema(vals, 14),
        "deltas": {
            "d1": _pct(full[-1]["smallcap"], full[-2]["smallcap"]) if len(full) >= 2 else None,
            "w1": _pct(full[-1]["smallcap"], full[-8]["smallcap"]) if len(full) >= 8 else None,
        },
        "regime": regime(vals),
        "launches": lad,
        "fear_greed": fg,
        "fg_history": fg_hist,
        "sources": sorted({r["source"] for r in ser}),
        "notes": notes + fg["notes"],
    }
    _cache[key] = {"_t": time.time(), "data": data}
    return data


def cached(env) -> dict | None:
    hit = _cache.get(id(env.db))
    return hit["data"] if hit else None
