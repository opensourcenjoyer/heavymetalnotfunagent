"""RugCheck public API (keyless)."""

from __future__ import annotations

import httpx

BASE = "https://api.rugcheck.xyz/v1"


class RugCheck:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def summary(self, mint: str) -> dict:
        r = await self.http.get(f"{BASE}/tokens/{mint}/report/summary", timeout=25)
        r.raise_for_status()
        d = r.json()
        return {
            "score_normalised": d.get("score_normalised"),  # 0 (good) .. 100 (bad)
            "score": d.get("score"),
            "lp_locked_pct": d.get("lpLockedPct"),
            "token_program": d.get("tokenProgram"),
            "risks": [
                {
                    "name": x.get("name"),
                    "level": x.get("level"),
                    "description": x.get("description"),
                    "value": x.get("value"),
                }
                for x in d.get("risks") or []
            ],
        }

    async def report(self, mint: str) -> dict:
        """Selected fields from the full report (it is large)."""
        r = await self.http.get(f"{BASE}/tokens/{mint}/report", timeout=30)
        r.raise_for_status()
        d = r.json()
        meta = d.get("tokenMeta") or {}
        holders = d.get("topHolders") or []
        return {
            "name": meta.get("name"),
            "symbol": meta.get("symbol"),
            "mutable_metadata": meta.get("mutable"),
            "mint_authority": d.get("mintAuthority"),
            "freeze_authority": d.get("freezeAuthority"),
            "creator": d.get("creator"),
            "rugged": d.get("rugged"),
            "total_holders": d.get("totalHolders"),
            "top10_pct": round(sum(h.get("pct", 0) for h in holders[:10]), 2) if holders else None,
            "insiders_detected": d.get("graphInsidersDetected"),
            "total_market_liquidity": d.get("totalMarketLiquidity"),
        }
