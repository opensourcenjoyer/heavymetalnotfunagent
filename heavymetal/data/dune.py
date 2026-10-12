"""Dune Analytics (API key): full-population Solana smallcap volume for Trenches.

Setup: create a query on dune.com with TRENCHES_SQL (`/trenches sql` prints it), schedule it daily,
then `/keys set dune` and `/keys set dune_query_id`. We only read the latest result (cheap), and
page through it: Dune caps a page at 32,000 rows, and the tail is exactly the trenches.
"""

from __future__ import annotations

import asyncio

import httpx

from heavymetal.data.http import ConnectorError, MissingKey, TTLCache

BASE = "https://api.dune.com/api/v1"
PAGE = 32_000

# Per-token volume on Solana DEXes for the last complete UTC day. The meme side of each trade is the
# side that is not a major. Columns are what heavymetal/trenches/pulse.py reads.
TRENCHES_SQL = """-- heavymetal · Trenches: Solana per-token DEX volume, last complete UTC day
WITH majors AS (
  SELECT mint FROM (VALUES
    ('So11111111111111111111111111111111111111112'),   -- wSOL
    ('EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'),  -- USDC
    ('Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB'),  -- USDT
    ('USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB'),   -- USD1
    ('2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo'),  -- PYUSD
    ('J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn'),  -- JitoSOL
    ('mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So'),   -- mSOL
    ('bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1'),   -- bSOL
    ('jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v'),   -- jupSOL
    ('5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm'),  -- INF
    ('cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij'),   -- cbBTC
    ('3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh'),  -- WBTC
    ('7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs')   -- WETH
  ) AS t(mint)
),
t AS (
  SELECT
    CASE WHEN token_bought_mint_address IN (SELECT mint FROM majors)
         THEN token_sold_mint_address ELSE token_bought_mint_address END AS mint,
    CASE WHEN token_bought_mint_address IN (SELECT mint FROM majors)
         THEN token_sold_symbol ELSE token_bought_symbol END AS symbol,
    (token_bought_mint_address IN (SELECT mint FROM majors)
     AND token_sold_mint_address IN (SELECT mint FROM majors)) AS both_major,
    amount_usd, trader_id, fee_tier, tx_id
  FROM dex_solana.trades
  WHERE block_time >= date_trunc('day', now()) - interval '1' day
    AND block_time < date_trunc('day', now())
    AND amount_usd > 0
)
SELECT
  CAST(date_trunc('day', now()) - interval '1' day AS date) AS day,
  mint,
  max(symbol) AS symbol,
  sum(amount_usd) AS volume_usd,
  count(*) AS swaps,
  count(DISTINCT trader_id) AS traders,
  min(fee_tier) AS min_fee_tier
FROM t
WHERE NOT both_major
GROUP BY 2
HAVING sum(amount_usd) >= 1000
ORDER BY volume_usd DESC
"""


class Dune:
    def __init__(self, http: httpx.AsyncClient, key_fn):
        self.http = http
        self.key_fn = key_fn  # callable -> current key (so /keys set takes effect without restart)
        self.cache = TTLCache(1800)

    def _headers(self) -> dict:
        key = self.key_fn()
        if not key:
            raise MissingKey("dune")
        return {"X-Dune-API-Key": key}

    async def latest_results(self, query_id: str, max_rows: int = 300_000) -> dict:
        """{'rows': [...], 'complete': bool, 'total': int|None, 'ended_at': str|None}"""
        hit = self.cache.get(query_id)
        if hit is not None:
            return hit
        headers, rows, offset, total, ended = self._headers(), [], 0, None, None
        while offset < max_rows:
            r = await self.http.get(
                f"{BASE}/query/{query_id}/results",
                params={"limit": PAGE, "offset": offset},
                headers=headers,
                timeout=60,
            )
            if r.status_code in (401, 403):
                raise ConnectorError(f"dune rejected the key ({r.status_code})")
            r.raise_for_status()
            d = r.json()
            res = d.get("result") or {}
            page = res.get("rows") or []
            rows += page
            total = (res.get("metadata") or {}).get("total_row_count", total)
            ended = d.get("execution_ended_at", ended)
            nxt = d.get("next_offset")
            if not page or nxt is None:
                break
            offset = nxt
        out = {"rows": rows, "complete": total is None or len(rows) >= total, "total": total, "ended_at": ended}
        return self.cache.put(query_id, out)

    async def execute(self, query_id: str, timeout_s: float = 300) -> dict:
        """Run the query now (costs credits) and wait for it."""
        headers = self._headers()
        r = await self.http.post(f"{BASE}/query/{query_id}/execute", headers=headers, timeout=30)
        r.raise_for_status()
        eid = r.json()["execution_id"]
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout_s
        while loop.time() < end:
            s = (await self.http.get(f"{BASE}/execution/{eid}/status", headers=headers, timeout=30)).json()
            state = s.get("state", "")
            if state == "QUERY_STATE_COMPLETED":
                self.cache.data.pop(query_id, None)
                return await self.latest_results(query_id)
            if state in ("QUERY_STATE_FAILED", "QUERY_STATE_CANCELLED", "QUERY_STATE_EXPIRED"):
                raise ConnectorError(f"dune execution {state}: {s.get('error')}")
            await asyncio.sleep(5)
        raise ConnectorError("dune execution timed out")
