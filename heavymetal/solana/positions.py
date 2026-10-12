"""Position management & TP/SL engine:
Calculates take-profit and stop-loss targets, tracks live PnL against current prices,
and executes exit sales when targets trigger or on user command.
"""

from __future__ import annotations

import asyncio
from typing import Any


def compute_targets(
    entry_price_usd: float | None, tp_multiple: float | None = 2.0, sl_pct: float | None = 30.0
) -> tuple[float | None, float | None]:
    if not entry_price_usd or entry_price_usd <= 0:
        return None, None
    tp_price = round(entry_price_usd * tp_multiple, 8) if tp_multiple and tp_multiple > 1.0 else None
    sl_price = round(entry_price_usd * (1.0 - (sl_pct / 100.0)), 8) if sl_pct and 0 < sl_pct < 100 else None
    return tp_price, sl_price


async def get_current_token_price(env, mint: str) -> float | None:
    """Fetch live price for a token mint from DexScreener."""
    try:
        pairs = await env.dex.token_pairs(mint)
        if pairs and pairs[0].get("price_usd"):
            return float(pairs[0]["price_usd"])
    except Exception:  # noqa: BLE001
        pass
    return None


async def track_new_position(
    env,
    mint: str,
    symbol: str,
    sol_amount: float,
    token_amount: float | None = None,
    entry_price_usd: float | None = None,
    tp_multiple: float | None = 2.0,
    sl_pct: float | None = 30.0,
    notes: str = "",
) -> dict:
    """Register an open trade in SQLite with Take-Profit and Stop-Loss prices."""
    if entry_price_usd is None:
        entry_price_usd = await get_current_token_price(env, mint)

    tp_price, sl_price = compute_targets(entry_price_usd, tp_multiple, sl_pct)

    pos_id = env.db.add_position(
        session_id=env.session_id,
        mint=mint,
        symbol=symbol or "TOKEN",
        entry_price_usd=entry_price_usd,
        token_amount=token_amount,
        sol_invested=sol_amount,
        tp_multiple=tp_multiple,
        sl_pct=sl_pct,
        tp_price_usd=tp_price,
        sl_price_usd=sl_price,
        notes=notes,
    )

    return {
        "position_id": pos_id,
        "mint": mint,
        "symbol": symbol,
        "sol_invested": sol_amount,
        "token_amount": token_amount,
        "entry_price_usd": entry_price_usd,
        "tp_multiple": tp_multiple,
        "tp_price_usd": tp_price,
        "sl_pct": sl_pct,
        "sl_price_usd": sl_price,
        "status": "OPEN",
    }


async def evaluate_open_positions(env) -> list[dict[str, Any]]:
    """Check all open positions against live market prices and determine if TP or SL is triggered."""
    open_pos = env.db.open_positions()
    if not open_pos:
        return []

    async def check_one(p: dict) -> dict:
        mint = p["mint"]
        curr_price = await get_current_token_price(env, mint)
        entry_price = p.get("entry_price_usd")
        tp_price = p.get("tp_price_usd")
        sl_price = p.get("sl_price_usd")

        pnl_pct = None
        action_trigger = "HOLD"
        if curr_price and entry_price and entry_price > 0:
            pnl_pct = round(((curr_price - entry_price) / entry_price) * 100, 2)
            if tp_price and curr_price >= tp_price:
                action_trigger = "TRIGGER_TP"
            elif sl_price and curr_price <= sl_price:
                action_trigger = "TRIGGER_SL"

        return {
            **p,
            "current_price_usd": curr_price,
            "pnl_pct": pnl_pct,
            "action_trigger": action_trigger,
        }

    return await asyncio.gather(*(check_one(p) for p in open_pos))
