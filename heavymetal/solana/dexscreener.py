"""Dexscreener public API (keyless, ~60-300 req/min)."""

from __future__ import annotations

import time

import httpx

BASE = "https://api.dexscreener.com"


def summarize_pair(p: dict) -> dict:
    created = p.get("pairCreatedAt")
    age_h = round((time.time() * 1000 - created) / 3_600_000, 1) if created else None
    tx = p.get("txns") or {}
    info = p.get("info") or {}
    price_usd = float(p["priceUsd"]) if p.get("priceUsd") else None
    price_native = float(p["priceNative"]) if p.get("priceNative") else None
    quote = (p.get("quoteToken") or {}).get("symbol")
    return {
        "pair": p.get("pairAddress"),
        "dex": p.get("dexId"),
        "labels": p.get("labels"),
        "base": {k: (p.get("baseToken") or {}).get(k) for k in ("address", "symbol", "name")},
        "quote": quote,
        "price_usd": price_usd,
        "price_native": price_native,
        "sol_usd": round(price_usd / price_native, 2) if price_usd and price_native and quote == "SOL" else None,
        "liquidity_usd": (p.get("liquidity") or {}).get("usd"),
        "fdv": p.get("fdv"),
        "market_cap": p.get("marketCap"),
        "volume": p.get("volume"),
        "price_change": p.get("priceChange"),
        "txns_h1": tx.get("h1"),
        "txns_h24": tx.get("h24"),
        "age_hours": age_h,
        "socials": [s.get("type") + ":" + (s.get("url") or s.get("handle") or "") for s in info.get("socials") or []],
        "websites": [w.get("url") for w in info.get("websites") or []],
        "boosts": (p.get("boosts") or {}).get("active"),
        "url": p.get("url"),
    }


class Dexscreener:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def _get(self, path: str, params: dict | None = None):
        r = await self.http.get(BASE + path, params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    async def token_pairs(self, mint: str) -> list[dict]:
        data = await self._get(f"/tokens/v1/solana/{mint}")
        pairs = data if isinstance(data, list) else data.get("pairs") or []
        pairs = sorted(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0, reverse=True)
        return [summarize_pair(p) for p in pairs]

    async def tokens_batch(self, mints: list[str]) -> dict[str, dict]:
        """Most liquid pair per mint, up to 30 mints per request."""
        out: dict[str, dict] = {}
        for i in range(0, len(mints), 30):
            chunk = mints[i : i + 30]
            data = await self._get(f"/tokens/v1/solana/{','.join(chunk)}")
            pairs = data if isinstance(data, list) else data.get("pairs") or []
            for p in pairs:
                mint = (p.get("baseToken") or {}).get("address")
                if mint not in chunk:
                    continue
                liq = (p.get("liquidity") or {}).get("usd") or 0
                if mint not in out or liq > (out[mint].get("liquidity_usd") or 0):
                    out[mint] = summarize_pair(p)
        return out

    async def pair(self, pair_address: str) -> dict | None:
        data = await self._get(f"/latest/dex/pairs/solana/{pair_address}")
        pairs = data.get("pairs") or ([data["pair"]] if data.get("pair") else [])
        return summarize_pair(pairs[0]) if pairs else None

    async def search(self, q: str, limit: int = 10) -> list[dict]:
        data = await self._get("/latest/dex/search", {"q": q})
        pairs = [p for p in data.get("pairs") or [] if p.get("chainId") == "solana"]
        pairs.sort(key=lambda p: (p.get("liquidity") or {}).get("usd") or 0, reverse=True)
        return [summarize_pair(p) for p in pairs[:limit]]

    async def top_boosted(self, limit: int = 15) -> list[dict]:
        data = await self._get("/token-boosts/top/v1")
        rows = [d for d in data if d.get("chainId") == "solana"][:limit]
        return [
            {
                "mint": d.get("tokenAddress"),
                "boost_total": d.get("totalAmount"),
                "description": (d.get("description") or "")[:200],
                "url": d.get("url"),
            }
            for d in rows
        ]

    async def latest_profiles(self, limit: int = 15) -> list[dict]:
        data = await self._get("/token-profiles/latest/v1")
        rows = [d for d in data if d.get("chainId") == "solana"][:limit]
        return [
            {"mint": d.get("tokenAddress"), "description": (d.get("description") or "")[:200], "url": d.get("url")}
            for d in rows
        ]
