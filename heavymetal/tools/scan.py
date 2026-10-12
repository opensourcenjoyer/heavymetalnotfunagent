"""Scan any wallet: holdings + recent activity summarized from parsed transactions."""

from __future__ import annotations

import asyncio

from heavymetal.solana.constants import LAMPORTS_PER_SOL, is_valid_pubkey
from heavymetal.tools.registry import err, ok, tool
from heavymetal.tools.wallet import holdings


def summarize_tx(tx: dict, owner: str) -> dict:
    meta = tx.get("meta") or {}
    msg = tx["transaction"]["message"]
    keys = [k["pubkey"] if isinstance(k, dict) else k for k in msg["accountKeys"]]
    sol_delta = None
    if owner in keys:
        i = keys.index(owner)
        sol_delta = (meta["postBalances"][i] - meta["preBalances"][i]) / LAMPORTS_PER_SOL
    changes: dict[str, float] = {}
    for side, sign in (("preTokenBalances", -1), ("postTokenBalances", 1)):
        for b in meta.get(side) or []:
            if b.get("owner") == owner:
                amt = float(b["uiTokenAmount"].get("uiAmountString") or 0)
                changes[b["mint"]] = changes.get(b["mint"], 0) + sign * amt
    token_deltas = {m: round(v, 6) for m, v in changes.items() if abs(v) > 0}
    programs = {ix.get("program") or ix.get("programId") for ix in msg.get("instructions", [])}
    kind = "other"
    if token_deltas and sol_delta is not None:
        up = any(v > 0 for v in token_deltas.values())
        down = any(v < 0 for v in token_deltas.values())
        if up and sol_delta < 0:
            kind = "buy"
        elif down and sol_delta > 0:
            kind = "sell"
        elif up and down:
            kind = "swap"
        else:
            kind = "token_transfer_in" if up else "token_transfer_out"
    elif sol_delta:
        kind = "sol_in" if sol_delta > 0 else "sol_out"
    return {
        "signature": tx["transaction"]["signatures"][0],
        "time": tx.get("blockTime"),
        "kind": kind,
        "sol_delta": round(sol_delta, 6) if sol_delta is not None else None,
        "token_deltas": token_deltas,
        "failed": meta.get("err") is not None,
        "programs": sorted(p for p in programs if p)[:6],
    }


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
