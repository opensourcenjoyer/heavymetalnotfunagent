"""PumpPortal Local Transaction API: we get an unsigned tx, sign locally, send via our own RPC.
Fee: 0.5% per trade (charged by PumpPortal). Pools: pump, raydium, pump-amm, launchlab, raydium-cpmm, bonk, auto.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import websockets

TRADE_LOCAL = "https://pumpportal.fun/api/trade-local"
DATA_WS = "wss://pumpportal.fun/api/data"


class PumpPortalError(RuntimeError):
    pass


class PumpPortal:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def build(self, body: dict) -> bytes:
        r = await self.http.post(TRADE_LOCAL, json=body, timeout=30)
        if r.status_code != 200:
            raise PumpPortalError(f"trade-local {r.status_code}: {r.text[:300] or r.reason_phrase}")
        return r.content

    async def trade_tx(
        self,
        public_key: str,
        action: str,
        mint: str,
        amount: float | str,
        denominated_in_sol: bool,
        slippage_pct: float,
        priority_fee_sol: float,
        pool: str = "auto",
    ) -> bytes:
        return await self.build(
            {
                "publicKey": public_key,
                "action": action,
                "mint": mint,
                "amount": amount,
                "denominatedInSol": "true" if denominated_in_sol else "false",
                "slippage": slippage_pct,
                "priorityFee": priority_fee_sol,
                "pool": pool,
            }
        )

    async def create_tx(
        self,
        public_key: str,
        mint: str,
        name: str,
        symbol: str,
        uri: str,
        dev_buy_sol: float,
        slippage_pct: float,
        priority_fee_sol: float,
        pool: str,
    ) -> bytes:
        return await self.build(
            {
                "publicKey": public_key,
                "action": "create",
                "mint": mint,
                "tokenMetadata": {"name": name, "symbol": symbol, "uri": uri},
                "denominatedInSol": "true",
                "amount": dev_buy_sol,
                "slippage": slippage_pct,
                "priorityFee": priority_fee_sol,
                "pool": pool,
            }
        )

    async def collect_fee_tx(
        self, public_key: str, priority_fee_sol: float, pool: str = "pump", mint: str | None = None
    ) -> bytes:
        body = {"publicKey": public_key, "action": "collectCreatorFee", "priorityFee": priority_fee_sol, "pool": pool}
        if mint:
            body["mint"] = mint
        return await self.build(body)

    async def new_tokens(self, seconds: float = 15, limit: int = 20) -> list[dict]:
        """Listen to the free subscribeNewToken stream for a short window."""
        out: list[dict] = []
        try:
            async with websockets.connect(DATA_WS, open_timeout=10) as ws:
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                loop = asyncio.get_running_loop()
                end = loop.time() + seconds
                while len(out) < limit and loop.time() < end:
                    try:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=end - loop.time()))
                    except TimeoutError:
                        break
                    if msg.get("txType") == "create" or ("mint" in msg and "name" in msg):
                        out.append(
                            {
                                k: msg.get(k)
                                for k in (
                                    "mint",
                                    "name",
                                    "symbol",
                                    "traderPublicKey",
                                    "initialBuy",
                                    "solAmount",
                                    "marketCapSol",
                                    "pool",
                                    "uri",
                                )
                            }
                        )
        except (OSError, websockets.WebSocketException) as e:
            raise PumpPortalError(f"websocket: {e}") from e
        return out
