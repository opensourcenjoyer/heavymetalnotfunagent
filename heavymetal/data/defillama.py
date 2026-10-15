"""DefiLlama (keyless): whole-chain daily DEX volume (Trenches backfill) and protocol TVL/fees (Wizzy facts)."""

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
        self.protocols_cache = TTLCache(6 * 3600)

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

    async def _protocols(self) -> list[dict]:
        hit = self.protocols_cache.get("all")
        if hit is not None:
            return hit
        r = await self.http.get(f"{BASE}/protocols", timeout=60)
        r.raise_for_status()
        rows = [
            {
                "slug": p.get("slug"),
                "name": p.get("name"),
                "address": (p.get("address") or "").strip(),
                "tvl": p.get("tvl"),
                "chains": p.get("chains") or [],
                "category": p.get("category"),
            }
            for p in r.json()
            if p.get("address")
        ]
        return self.protocols_cache.put("all", rows)

    async def protocol_for_token(self, mint: str) -> dict | None:
        """The protocol whose governance/native token is this Solana mint, if DefiLlama maps one."""
        for p in await self._protocols():
            addr = p["address"]
            if addr == mint or addr == f"solana:{mint}":
                return p
        return None

    async def protocol_fees_24h(self, slug: str) -> float | None:
        ck = f"fees:{slug}"
        hit = self.cache.get(ck)
        if hit is not None:
            return hit
        r = await self.http.get(f"{BASE}/summary/fees/{slug}", params={"dataType": "dailyFees"}, timeout=30)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        v = r.json().get("total24h")
        return self.cache.put(ck, float(v) if v is not None else None)
