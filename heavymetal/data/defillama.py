"""DefiLlama (keyless): whole-chain daily DEX volume, used to backfill Trenches history."""

from __future__ import annotations

import datetime as dt

import httpx

from heavymetal.data.http import TTLCache

BASE = "https://api.llama.fi"


def day_str(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%Y-%m-%d")


class DefiLlama:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http
        self.cache = TTLCache(3600)

    async def chain_dex_volume(self, chain: str = "solana") -> dict:
        """{'days': [(YYYY-MM-DD, usd), ...] oldest first, 'total24h': float|None}"""
        hit = self.cache.get(chain)
        if hit is not None:
            return hit
        r = await self.http.get(
            f"{BASE}/overview/dexs/{chain}",
            params={
                "excludeTotalDataChart": "false",
                "excludeTotalDataChartBreakdown": "true",
                "dataType": "dailyVolume",
            },
            timeout=30,
        )
        r.raise_for_status()
        d = r.json()
        days = [(day_str(ts), float(v)) for ts, v in d.get("totalDataChart") or [] if v is not None]
        return self.cache.put(chain, {"days": days, "total24h": d.get("total24h")})
