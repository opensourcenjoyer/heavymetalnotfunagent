"""Scan any wallet: holdings + recent activity summarized from parsed transactions."""

from __future__ import annotations

import asyncio

from heavymetal.solana.constants import is_valid_pubkey
from heavymetal.solana.holdings import holdings
from heavymetal.solana.txsummary import summarize_tx
from heavymetal.tools.registry import err, ok, tool


@tool(
    "scan_wallet",
    "Analyze any Solana wallet: SOL + token holdings (USD) and a summary of its most recent "
    "transactions (buys, sells, transfers, SOL flow).",
    {"address": {"type": "string"}, "limit": {"type": "integer", "default": 15, "description": "txs, max 40"}},
    ["address"],
)
async def scan_wallet(env, address: str, limit: int = 15):
    if not is_valid_pubkey(address):
        return err("invalid address")
    hold = await holdings(env, address)
    sigs = await env.rpc.signatures(address, min(limit, 40))
    sem = asyncio.Semaphore(5)

    async def fetch(s):
        async with sem:
            try:
                return await env.rpc.transaction(s["signature"])
            except Exception:  # noqa: BLE001
                return None

    txs = await asyncio.gather(*(fetch(s) for s in sigs))
    acts = [summarize_tx(t, address) for t in txs if t]
    counts: dict[str, int] = {}
    for a in acts:
        counts[a["kind"]] = counts.get(a["kind"], 0) + 1
    net_sol = round(sum(a["sol_delta"] or 0 for a in acts), 6)
    return ok(
        holdings=hold,
        recent=acts,
        activity_counts=counts,
        net_sol_recent=net_sol,
        oldest_scanned=sigs[-1].get("blockTime") if sigs else None,
    )
