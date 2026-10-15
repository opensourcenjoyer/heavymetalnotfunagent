"""Birdeye (API key): token overview with unique wallets (farm filter) and hourly OHLCV (Wizzy facts)."""

from __future__ import annotations

import time

import httpx

from heavymetal.data.http import ConnectorError, MissingKey, RateLimiter, TTLCache, fnum

BASE = "https://public-api.birdeye.so"


class Birdeye:
    def __init__(self, http: httpx.AsyncClient, key_fn):
        self.http = http
        self.key_fn = key_fn
        self.limit = RateLimiter(50, 60)
        self.cache = TTLCache(120)

    @property
    def enabled(self) -> bool:
        return bool(self.key_fn())

    async def token_overview(self, mint: str) -> dict:
        key = self.key_fn()
        if not key:
            raise MissingKey("birdeye")
        hit = self.cache.get(mint)
        if hit is not None:
            return hit
        await self.limit.wait()
        r = await self.http.get(
            f"{BASE}/defi/token_overview",
            params={"address": mint},
            headers={"X-API-KEY": key, "x-chain": "solana", "accept": "application/json"},
            timeout=20,
        )
        if r.status_code in (401, 403):
            raise ConnectorError(f"birdeye rejected the key ({r.status_code})")
        r.raise_for_status()
        d = r.json().get("data") or {}
        return self.cache.put(
            mint,
            {
                "unique_wallets_24h": fnum(d.get("uniqueWallet24h")),
                "trades_24h": fnum(d.get("trade24h")),
                "buys_24h": fnum(d.get("buy24h")),
                "sells_24h": fnum(d.get("sell24h")),
                "volume_24h": fnum(d.get("v24hUSD")),
                "liquidity_usd": fnum(d.get("liquidity")),
                "market_cap": fnum(d.get("mc") or d.get("marketCap")),
            },
        )

    async def ohlcv_hourly(self, mint: str, hours: int = 24) -> list[dict]:
        """Hourly candles oldest -> newest: {ts, open, high, low, close, volume} (volume in USD)."""
        key = self.key_fn()
        if not key:
            raise MissingKey("birdeye")
        ck = f"ohlcv:{mint}:{hours}"
        hit = self.cache.get(ck)
        if hit is not None:
            return hit
        await self.limit.wait()
        now = int(time.time())
        r = await self.http.get(
            f"{BASE}/defi/ohlcv",
            params={"address": mint, "type": "1H", "time_from": now - hours * 3600, "time_to": now},
            headers={"X-API-KEY": key, "x-chain": "solana", "accept": "application/json"},
            timeout=20,
        )
        if r.status_code in (401, 403):
            raise ConnectorError(f"birdeye rejected the key ({r.status_code})")
        r.raise_for_status()
        items = (r.json().get("data") or {}).get("items") or []
        candles = [
            {
                "ts": int(i.get("unixTime") or 0),
                "open": fnum(i.get("o")),
                "high": fnum(i.get("h")),
                "low": fnum(i.get("l")),
                "close": fnum(i.get("c")),
                "volume": fnum(i.get("v")),
            }
            for i in items
        ]
        candles.sort(key=lambda c: c["ts"])
        return self.cache.put(ck, candles)
