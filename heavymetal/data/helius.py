"""Helius (API key): parsed swaps on a pool, to measure swaps per wallet (fee farming / round-tripping)."""

from __future__ import annotations

from collections import Counter

import httpx

from heavymetal.data.http import ConnectorError, MissingKey, RateLimiter, TTLCache

BASE = "https://api.helius.xyz/v0"


def swaps_per_wallet(txs: list[dict]) -> dict:
    """From a sample of parsed SWAP txs: wallets, swaps per wallet scaled to a day, and the top churners."""
    payers = Counter(t.get("feePayer") for t in txs if t.get("feePayer"))
    stamps = [t["timestamp"] for t in txs if t.get("timestamp")]
    if not payers or len(stamps) < 2:
        return {"sample": len(txs), "wallets": len(payers), "swaps_per_wallet_day": None, "top": []}
    span_h = max((max(stamps) - min(stamps)) / 3600, 0.25)
    per_wallet = len(txs) / len(payers)
    return {
        "sample": len(txs),
        "span_hours": round(span_h, 2),
        "wallets": len(payers),
        "swaps_per_wallet": round(per_wallet, 2),
        "swaps_per_wallet_day": round(per_wallet * 24 / span_h, 1),
        "top_wallet_share": round(payers.most_common(1)[0][1] / len(txs), 3),
        "top": [{"wallet": w, "swaps": n} for w, n in payers.most_common(5)],
    }


class Helius:
    def __init__(self, http: httpx.AsyncClient, key_fn):
        self.http = http
        self.key_fn = key_fn
        self.limit = RateLimiter(60, 60)
        self.cache = TTLCache(300)

    @property
    def enabled(self) -> bool:
        return bool(self.key_fn())

    async def pool_swaps(self, address: str, limit: int = 100) -> dict:
        key = self.key_fn()
        if not key:
            raise MissingKey("helius")
        hit = self.cache.get(address)
        if hit is not None:
            return hit
        await self.limit.wait()
        r = await self.http.get(
            f"{BASE}/addresses/{address}/transactions",
            params={"api-key": key, "type": "SWAP", "limit": min(limit, 100)},
            timeout=30,
        )
        if r.status_code in (401, 403):
            raise ConnectorError(f"helius rejected the key ({r.status_code})")
        r.raise_for_status()
        txs = r.json() if isinstance(r.json(), list) else []
        return self.cache.put(address, swaps_per_wallet(txs))

    async def wallet_swaps(self, address: str, limit: int = 100) -> list[dict]:
        """A wallet's recent parsed swaps, summarized like solana.txsummary.summarize_tx (newest first)."""
        key = self.key_fn()
        if not key:
            raise MissingKey("helius")
        ck = f"wallet:{address}:{limit}"
        hit = self.cache.get(ck)
        if hit is not None:
            return hit
        await self.limit.wait()
        r = await self.http.get(
            f"{BASE}/addresses/{address}/transactions",
            params={"api-key": key, "type": "SWAP", "limit": min(limit, 100)},
            timeout=30,
        )
        if r.status_code in (401, 403):
            raise ConnectorError(f"helius rejected the key ({r.status_code})")
        r.raise_for_status()
        txs = r.json() if isinstance(r.json(), list) else []
        return self.cache.put(ck, [summarize_helius_tx(t, address) for t in txs])


def summarize_helius_tx(t: dict, owner: str) -> dict:
    deltas: dict[str, float] = {}
    for tr in t.get("tokenTransfers") or []:
        amt = float(tr.get("tokenAmount") or 0)
        if tr.get("toUserAccount") == owner:
            deltas[tr["mint"]] = deltas.get(tr["mint"], 0) + amt
        if tr.get("fromUserAccount") == owner:
            deltas[tr["mint"]] = deltas.get(tr["mint"], 0) - amt
    sol = 0.0
    for nt in t.get("nativeTransfers") or []:
        lamports = float(nt.get("amount") or 0) / 1e9
        if nt.get("toUserAccount") == owner:
            sol += lamports
        if nt.get("fromUserAccount") == owner:
            sol -= lamports
    deltas = {m: round(v, 6) for m, v in deltas.items() if abs(v) > 0}
    up = any(v > 0 for v in deltas.values())
    down = any(v < 0 for v in deltas.values())
    kind = "buy" if up and sol < 0 else "sell" if down and sol > 0 else "swap" if up or down else "other"
    return {
        "signature": t.get("signature"),
        "time": t.get("timestamp"),
        "kind": kind,
        "sol_delta": round(sol, 6),
        "token_deltas": deltas,
        "failed": bool(t.get("transactionError")),
    }
