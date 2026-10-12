"""Minimal async Solana JSON-RPC client (httpx). Works with any RPC: QuickNode, Helius, public."""

from __future__ import annotations

import asyncio
import base64
import itertools
from typing import Any

import httpx

from heavymetal.solana.constants import LAMPORTS_PER_SOL, TOKEN_2022_PROGRAM, TOKEN_PROGRAM


class RPCError(RuntimeError):
    """The node answered with a JSON-RPC error (not retried on other nodes)."""


class RPCUnavailable(RPCError):
    """Transport failure, HTTP 429/5xx or an unhealthy node: try the next node."""


UNHEALTHY_CODES = {-32005}  # node is behind / unhealthy


class RPC:
    """JSON-RPC client over a list of nodes on the same cluster.
    Calls go to the current node; on RPCUnavailable they fail over to the next one and stay there."""

    def __init__(self, urls: str | list[str], http: httpx.AsyncClient):
        self.http = http
        self._ids = itertools.count(1)
        self.on_failover = None  # callable(from_url, to_url, reason)
        self.set_urls(urls)

    def set_urls(self, urls: str | list[str]) -> None:
        self.urls = [urls] if isinstance(urls, str) else list(dict.fromkeys(urls))
        if not self.urls:
            raise ValueError("no RPC urls")
        self.i = 0

    @property
    def url(self) -> str:
        return self.urls[self.i]

    async def _one(self, url: str, payload: dict, attempts: int):
        last = ""
        for attempt in range(attempts):
            if attempt:
                await asyncio.sleep(0.4 * 2**attempt)
            try:
                r = await self.http.post(url, json=payload, timeout=30)
            except httpx.TransportError as e:
                last = f"{type(e).__name__}: {e}"
                continue
            if r.status_code == 429 or r.status_code >= 500:
                last = f"HTTP {r.status_code}"
                continue
            if r.status_code >= 400:
                raise RPCUnavailable(f"HTTP {r.status_code}: {r.text[:200]}")
            try:
                data = r.json()
            except ValueError:
                raise RPCUnavailable(f"non-JSON response: {r.text[:120]}") from None
            if "error" in data:
                e = data["error"]
                if isinstance(e, dict) and e.get("code") in UNHEALTHY_CODES:
                    last = f"unhealthy: {e.get('message')}"
                    continue
                raise RPCError(f"{payload['method']}: {e.get('message', e) if isinstance(e, dict) else e}")
            return data.get("result")
        raise RPCUnavailable(last or "unavailable")

    async def call(self, method: str, params: list | None = None) -> Any:
        payload = {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params or []}
        n = len(self.urls)
        errors = []
        for k in range(n):
            idx = (self.i + k) % n
            try:
                result = await self._one(self.urls[idx], payload, attempts=4 if n == 1 else 2)
            except RPCUnavailable as e:
                errors.append(f"{e}")
                continue
            if idx != self.i:
                old, self.i = self.urls[self.i], idx
                if callable(self.on_failover):
                    self.on_failover(old, self.urls[idx], errors[0] if errors else "")
            return result
        hint = " Add another node with /rpc add, or use a dedicated RPC like QuickNode." if n == 1 else ""
        raise RPCUnavailable(f"{method}: all {n} RPC node(s) failed ({'; '.join(errors)}).{hint}")

    # ---------------------------------------------------------------- reads
    async def balance_lamports(self, address: str) -> int:
        return (await self.call("getBalance", [address, {"commitment": "confirmed"}]))["value"]

    async def balance_sol(self, address: str) -> float:
        return await self.balance_lamports(address) / LAMPORTS_PER_SOL

    async def token_accounts(self, owner: str) -> list[dict]:
        """All SPL + Token-2022 holdings with non-zero balance: [{mint, amount, decimals, ui_amount, program}]"""
        out = []
        for program in (TOKEN_PROGRAM, TOKEN_2022_PROGRAM):
            res = await self.call(
                "getTokenAccountsByOwner",
                [owner, {"programId": str(program)}, {"encoding": "jsonParsed", "commitment": "confirmed"}],
            )
            for acc in res["value"]:
                info = acc["account"]["data"]["parsed"]["info"]
                ta = info["tokenAmount"]
                if int(ta["amount"]) == 0:
                    continue
                out.append(
                    {
                        "mint": info["mint"],
                        "account": acc["pubkey"],
                        "amount": int(ta["amount"]),
                        "decimals": ta["decimals"],
                        "ui_amount": float(ta.get("uiAmountString") or 0),
                        "program": str(program),
                    }
                )
        return out

    async def mint_info(self, mint: str) -> dict:
        """{decimals, supply, program, mint_authority, freeze_authority}"""
        res = await self.call("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
        if not res or not res.get("value"):
            raise RPCError(f"mint not found: {mint}")
        v = res["value"]
        parsed = v["data"].get("parsed") if isinstance(v["data"], dict) else None
        if not parsed or parsed.get("type") != "mint":
            raise RPCError(f"not a token mint: {mint}")
        info = parsed["info"]
        return {
            "decimals": info["decimals"],
            "supply": int(info["supply"]),
            "program": v["owner"],
            "mint_authority": info.get("mintAuthority"),
            "freeze_authority": info.get("freezeAuthority"),
        }

    async def largest_holders(self, mint: str) -> list[dict]:
        res = await self.call("getTokenLargestAccounts", [mint, {"commitment": "confirmed"}])
        return [
            {"account": a["address"], "amount": int(a["amount"]), "ui_amount": float(a.get("uiAmountString") or 0)}
            for a in res["value"]
        ]

    async def signatures(self, address: str, limit: int = 20) -> list[dict]:
        return await self.call("getSignaturesForAddress", [address, {"limit": limit}])

    async def transaction(self, sig: str) -> dict | None:
        return await self.call(
            "getTransaction",
            [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}],
        )

    async def latest_blockhash(self) -> tuple[str, int]:
        v = (await self.call("getLatestBlockhash", [{"commitment": "confirmed"}]))["value"]
        return v["blockhash"], v["lastValidBlockHeight"]

    async def block_height(self) -> int:
        return await self.call("getBlockHeight", [{"commitment": "confirmed"}])

    async def signature_status(self, sig: str) -> dict | None:
        res = await self.call("getSignatureStatuses", [[sig], {"searchTransactionHistory": True}])
        return res["value"][0]

    # ---------------------------------------------------------------- writes
    async def send_raw(self, raw: bytes, skip_preflight: bool = False) -> str:
        return await self.call(
            "sendTransaction",
            [
                base64.b64encode(raw).decode(),
                {
                    "encoding": "base64",
                    "skipPreflight": skip_preflight,
                    "preflightCommitment": "confirmed",
                    "maxRetries": 0,
                },
            ],
        )

    async def airdrop(self, address: str, lamports: int) -> str:
        return await self.call("requestAirdrop", [address, lamports])
