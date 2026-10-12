"""Jupiter Swap API v2 (Meta-Aggregator: /order + /execute). Works keyless at a lower rate limit."""

from __future__ import annotations

import base64

import httpx
from solders.keypair import Keypair

from heavymetal.solana.tx import sign_external

BASE = "https://api.jup.ag/swap/v2"
PRICE = "https://api.jup.ag/price/v3"


class JupiterError(RuntimeError):
    pass


class Jupiter:
    def __init__(self, http: httpx.AsyncClient, api_key: str = ""):
        self.http = http
        self.headers = {"x-api-key": api_key} if api_key else {}

    async def order(
        self, input_mint: str, output_mint: str, amount: int, taker: str | None = None, slippage_bps: int | None = None
    ) -> dict:
        params = {"inputMint": input_mint, "outputMint": output_mint, "amount": str(amount)}
        if taker:
            params["taker"] = taker
        if slippage_bps is not None:
            params["slippageBps"] = str(slippage_bps)
        r = await self.http.get(f"{BASE}/order", params=params, headers=self.headers, timeout=25)
        if r.status_code == 401:
            raise JupiterError("Jupiter requires an API key now: set keys.jupiter in config.toml")
        if r.status_code >= 400:
            raise JupiterError(f"/order {r.status_code}: {r.text[:300]}")
        return r.json()

    async def swap(
        self, kp: Keypair, input_mint: str, output_mint: str, amount: int, slippage_bps: int | None = None
    ) -> dict:
        order = await self.order(input_mint, output_mint, amount, str(kp.pubkey()), slippage_bps)
        if not order.get("transaction"):
            raise JupiterError(
                f"no transaction: [{order.get('router')}] {order.get('errorCode')} "
                f"{order.get('errorMessage') or order.get('error')}"
            )
        signed = sign_external(base64.b64decode(order["transaction"]), [kp])
        r = await self.http.post(
            f"{BASE}/execute",
            headers=self.headers,
            timeout=60,
            json={"signedTransaction": base64.b64encode(bytes(signed)).decode(), "requestId": order["requestId"]},
        )
        if r.status_code >= 400:
            raise JupiterError(f"/execute {r.status_code}: {r.text[:300]}")
        res = r.json()
        return {
            "status": "confirmed" if res.get("status") == "Success" else "failed",
            "signature": res.get("signature") or str(signed.signatures[0]),
            "code": res.get("code"),
            "error": res.get("error"),
            "in_amount": res.get("totalInputAmount"),
            "out_amount": res.get("totalOutputAmount"),
            "router": order.get("router"),
            "fee_bps": order.get("feeBps"),
        }

    async def prices(self, mints: list[str]) -> dict[str, float]:
        if not mints:
            return {}
        out: dict[str, float] = {}
        for i in range(0, len(mints), 50):
            r = await self.http.get(
                PRICE, params={"ids": ",".join(mints[i : i + 50])}, headers=self.headers, timeout=20
            )
            if r.status_code >= 400:
                continue
            for mint, v in (r.json() or {}).items():
                if isinstance(v, dict) and v.get("usdPrice") is not None:
                    out[mint] = float(v["usdPrice"])
        return out
