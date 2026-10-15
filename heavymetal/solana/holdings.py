"""Holdings of any wallet: SOL + SPL/Token-2022 balances with USD values (Jupiter prices, mainnet only).

Lives outside ``heavymetal.tools`` so read-only callers (e.g. the Wizzy bot) can use it without importing the
tool registry, which registers the trading and transfer tools.
"""

from __future__ import annotations

from heavymetal.solana.constants import SOL_MINT


async def holdings(env, address: str) -> dict:
    sol = await env.rpc.balance_sol(address)
    tokens = await env.rpc.token_accounts(address)
    prices = {}
    if env.cluster == "mainnet":
        try:
            prices = await env.jup.prices([SOL_MINT] + [t["mint"] for t in tokens])
        except Exception:  # noqa: BLE001 - prices are best-effort
            prices = {}
    total = sol * prices.get(SOL_MINT, 0)
    rows = []
    for t in sorted(tokens, key=lambda t: -t["ui_amount"] * prices.get(t["mint"], 0)):
        usd = t["ui_amount"] * prices[t["mint"]] if t["mint"] in prices else None
        total += usd or 0
        rows.append(
            {
                "mint": t["mint"],
                "amount": t["ui_amount"],
                "decimals": t["decimals"],
                "usd": round(usd, 2) if usd is not None else None,
            }
        )
    return {
        "address": address,
        "sol": sol,
        "sol_usd_price": prices.get(SOL_MINT),
        "tokens": rows,
        "total_usd": round(total, 2) if prices else None,
    }
