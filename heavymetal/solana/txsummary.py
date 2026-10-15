"""Summarize one parsed transaction from a wallet's point of view (buy, sell, swap, transfer, SOL flow).

Lives outside ``heavymetal.tools`` so read-only callers can use it without importing the tool registry.
"""

from __future__ import annotations

from heavymetal.solana.constants import LAMPORTS_PER_SOL


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
