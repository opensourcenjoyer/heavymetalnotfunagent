"""GeckoTerminal public API v2 (keyless, ~30 req/min). Pools, new pools, OHLCV.

Every pool is normalised to one flat dict (see `normalize_pool`) so the farm filter, the scanner
and Trenches all read the same field names.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime

import httpx

from heavymetal.data.http import ConnectorError, RateLimiter, TTLCache, fnum

BASE = "https://api.geckoterminal.com/api/v2"
NETWORK = "solana"
WINDOWS = ("m5", "h1", "h6", "h24")


def _iso_ts(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _tok_id(rel: dict | None) -> str | None:
    tid = ((rel or {}).get("data") or {}).get("id") or ""
    return tid.split("_", 1)[1] if "_" in tid else (tid or None)


def normalize_pool(p: dict, tokens: dict[str, dict] | None = None) -> dict:
    a = p.get("attributes") or {}
    rel = p.get("relationships") or {}
    tokens = tokens or {}
    base_mint, quote_mint = _tok_id(rel.get("base_token")), _tok_id(rel.get("quote_token"))
    base, quote = tokens.get(base_mint) or {}, tokens.get(quote_mint) or {}
    name = a.get("name") or ""
    left, _, right = name.partition(" / ")
    tx = a.get("transactions") or {}
    created = _iso_ts(a.get("pool_created_at"))
    return {
        "pool": a.get("address"),
        "mint": base_mint,
        "symbol": base.get("symbol") or left.strip() or None,
        "name": base.get("name"),
        "quote_mint": quote_mint,
        "quote_symbol": quote.get("symbol") or right.strip() or None,
        "dex": _tok_id(rel.get("dex")) or ((rel.get("dex") or {}).get("data") or {}).get("id"),
        "price_usd": fnum(a.get("base_token_price_usd")),
        "fdv": fnum(a.get("fdv_usd")),
        "market_cap": fnum(a.get("market_cap_usd")),
        "liquidity_usd": fnum(a.get("reserve_in_usd")),
        "created_ts": created,
        "age_hours": round((time.time() - created) / 3600, 2) if created else None,
        "volume": {w: fnum((a.get("volume_usd") or {}).get(w)) for w in WINDOWS},
        "price_change": {w: fnum((a.get("price_change_percentage") or {}).get(w)) for w in WINDOWS},
        "txns": {
            w: {k: int((tx.get(w) or {}).get(k) or 0) for k in ("buys", "sells", "buyers", "sellers")}
            for w in ("h1", "h24")
        },
        "source": "gt",
    }


class GeckoTerminal:
    def __init__(self, http: httpx.AsyncClient, rate_per_min: int = 20):
        self.http = http
        self.limit = RateLimiter(rate_per_min, 60)
        self.cache = TTLCache(45)

    async def _get(self, path: str, params: dict | None = None, ttl_key: str | None = None):
        key = ttl_key or (path + repr(sorted((params or {}).items())))
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        for attempt in range(4):
            await self.limit.wait()
            r = await self.http.get(BASE + path, params=params, headers={"accept": "application/json"}, timeout=25)
            if r.status_code != 429:
                break
            await asyncio.sleep(min(60, 8 * 2**attempt))  # public API: back off and retry
        if r.status_code == 429:
            raise ConnectorError("geckoterminal rate limited (429)")
        if r.status_code == 404:
            return self.cache.put(key, {"data": []})
        r.raise_for_status()
        return self.cache.put(key, r.json())

    @staticmethod
    def _rows(data: dict) -> list[dict]:
        tokens = {
            (t.get("attributes") or {}).get("address"): t.get("attributes") or {}
            for t in data.get("included") or []
            if t.get("type") == "token"
        }
        rows = data.get("data") or []
        return [normalize_pool(p, tokens) for p in (rows if isinstance(rows, list) else [rows])]

    async def top_pools(self, pages: int = 10) -> list[dict]:
        """The chain's most-traded pools by 24h volume (GeckoTerminal caps at 10 pages x 20 = 200)."""
        out: list[dict] = []
        for page in range(1, min(pages, 10) + 1):
            data = await self._get(
                f"/networks/{NETWORK}/pools",
                {"page": page, "sort": "h24_volume_usd_desc", "include": "base_token,quote_token,dex"},
            )
            rows = self._rows(data)
            out += rows
            if len(rows) < 20:
                break
        return out

    async def new_pools(self, pages: int = 1) -> list[dict]:
        out: list[dict] = []
        for page in range(1, min(pages, 10) + 1):
            out += self._rows(
                await self._get(
                    f"/networks/{NETWORK}/new_pools", {"page": page, "include": "base_token,quote_token,dex"}
                )
            )
        return out

    async def token_pools(self, mint: str) -> list[dict]:
        """Pools of one token, most liquid first."""
        rows = self._rows(
            await self._get(
                f"/networks/{NETWORK}/tokens/{mint}/pools", {"page": 1, "include": "base_token,quote_token,dex"}
            )
        )
        rows = [r for r in rows if r["mint"] == mint] or rows
        return sorted(rows, key=lambda r: r["liquidity_usd"] or 0, reverse=True)

    async def ohlcv(
        self, pool: str, timeframe: str = "hour", aggregate: int = 1, limit: int = 200, before_ts: int | None = None
    ) -> list[dict]:
        """Candles oldest -> newest: {ts, open, high, low, close, volume}."""
        params: dict = {"aggregate": aggregate, "limit": min(limit, 1000)}
        if before_ts:
            params["before_timestamp"] = int(before_ts)
        data = await self._get(f"/networks/{NETWORK}/pools/{pool}/ohlcv/{timeframe}", params)
        lst = (
            ((data.get("data") or {}).get("attributes") or {}).get("ohlcv_list")
            if isinstance(data.get("data"), dict)
            else []
        )
        rows = [
            {"ts": int(c[0]), "open": c[1], "high": c[2], "low": c[3], "close": c[4], "volume": c[5]}
            for c in lst or []
            if len(c) >= 6
        ]
        return sorted(rows, key=lambda c: c["ts"])
