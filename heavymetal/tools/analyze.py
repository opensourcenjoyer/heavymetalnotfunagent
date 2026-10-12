"""Market + safety analysis: Dexscreener, RugCheck, on-chain mint/holder data, pump.fun launch stream."""

from __future__ import annotations

import asyncio

from heavymetal.signals.audit import audit_mint
from heavymetal.signals.ledger import record_signal
from heavymetal.solana.constants import is_valid_pubkey
from heavymetal.solana.resolver import resolve_target
from heavymetal.tools.registry import err, ok, tool

MINT = {"mint": {"type": "string", "description": "token mint address"}}


@tool(
    "token_audit",
    "Comprehensive token audit: resolves DexScreener/pump.fun links, analyzes liquidity, volume buy/sell "
    "ratios, contract traps, fake/copycat spoofing, farm/wash volume, top holders, and generates a Bubblemaps "
    "link. Records the token in the signal ledger and returns related wiki pages.",
    {"target": {"type": "string", "description": "DexScreener URL, pump.fun URL, or token/pair address"}},
    ["target"],
    external=True,
)
async def token_audit(env, target: str):
    try:
        resolved = await resolve_target(env, target)
    except Exception as e:  # noqa: BLE001
        return err(f"failed to resolve target '{target}': {e}")

    res = await audit_mint(env, resolved.mint, resolved.symbol)
    if not res["market"].get("symbol") and resolved.symbol:
        res["market"]["symbol"] = resolved.symbol
    try:
        sid, is_new = record_signal(env.db, res, source="audit")
        res["signal"] = {"id": sid, "new": is_new}
    except Exception:  # noqa: BLE001 - the ledger must never break an audit
        pass
    try:
        from heavymetal.kb.wiki import refs_for_audit

        res["wiki_refs"] = refs_for_audit(res)
    except Exception:  # noqa: BLE001
        pass
    res.pop("features", None)
    return ok(resolved=resolved.to_dict(), **res)


# Alias for backward compatibility
@tool(
    "degen_audit",
    "Alias for token_audit.",
    {"target": {"type": "string", "description": "DexScreener URL, pump.fun URL, or token/pair address"}},
    ["target"],
    external=True,
)
async def degen_audit(env, target: str):
    return await token_audit(env, target)


@tool(
    "token_info",
    "Market data for a token: price, liquidity, volume, buys/sells, age, FDV, socials, top pools, "
    "plus on-chain mint/freeze authority and supply.",
    MINT,
    ["mint"],
    external=True,
)
async def token_info(env, mint: str):
    if not is_valid_pubkey(mint):
        return err("invalid mint address")
    pairs, chain = await asyncio.gather(env.dex.token_pairs(mint), env.rpc.mint_info(mint), return_exceptions=True)
    data = {"mint": mint}
    if isinstance(chain, Exception):
        data["onchain_error"] = str(chain)
    else:
        data.update(
            decimals=chain["decimals"],
            supply=chain["supply"] / 10 ** chain["decimals"],
            mint_authority=chain["mint_authority"],
            freeze_authority=chain["freeze_authority"],
            token_program=chain["program"],
        )
    if isinstance(pairs, Exception):
        data["market_error"] = str(pairs)
    else:
        data["pools"] = pairs[:3]
        data["pool_count"] = len(pairs)
        if not pairs:
            data["market_note"] = "no indexed pools yet (very new or bonding-curve only)"
    return ok(**data)


@tool(
    "search_tokens",
    "Search Solana tokens/pairs by ticker, name or address (Dexscreener).",
    {"query": {"type": "string"}, "limit": {"type": "integer", "default": 8}},
    ["query"],
    external=True,
)
async def search_tokens(env, query: str, limit: int = 8):
    return ok(results=await env.dex.search(query, min(limit, 20)))


@tool(
    "pool_info",
    "Details of one liquidity pool by pair address: liquidity, volume, txns, price change, age.",
    {"pair": {"type": "string", "description": "pool / pair address"}},
    ["pair"],
    external=True,
)
async def pool_info(env, pair: str):
    p = await env.dex.pair(pair)
    return ok(pool=p) if p else err("pair not found on Dexscreener")


@tool(
    "rug_check",
    "Safety report from RugCheck: risk score (0 good .. 100 bad), risks, LP locked %, "
    "mint/freeze authority, top-10 holder %, insiders.",
    MINT,
    ["mint"],
    external=True,
)
async def rug_check(env, mint: str):
    summary, report = await asyncio.gather(env.rug.summary(mint), env.rug.report(mint), return_exceptions=True)
    if isinstance(summary, Exception) and isinstance(report, Exception):
        return err(f"rugcheck unavailable: {summary}")
    out = {"mint": mint}
    if not isinstance(summary, Exception):
        out.update(summary)
    if not isinstance(report, Exception):
        out.update(report)
    return ok(**out)


@tool(
    "holders",
    "Top 20 token accounts and their share of supply (note: the largest is often the pool or bonding curve).",
    MINT,
    ["mint"],
)
async def holders(env, mint: str):
    info, top = await asyncio.gather(env.rpc.mint_info(mint), env.rpc.largest_holders(mint))
    supply = info["supply"] or 1
    rows = [
        {"account": h["account"], "amount": h["ui_amount"], "pct": round(100 * h["amount"] / supply, 2)} for h in top
    ]
    return ok(
        mint=mint,
        top=rows,
        top10_pct=round(sum(r["pct"] for r in rows[:10]), 2),
        top1_pct=rows[0]["pct"] if rows else None,
    )


@tool("trending", "Trending Solana tokens right now (Dexscreener top boosts + latest token profiles).", external=True)
async def trending(env):
    boosted, profiles = await asyncio.gather(env.dex.top_boosted(), env.dex.latest_profiles(), return_exceptions=True)
    return ok(
        top_boosted=boosted if not isinstance(boosted, Exception) else str(boosted),
        latest_profiles=profiles if not isinstance(profiles, Exception) else str(profiles),
    )


@tool(
    "new_launches",
    "Listen to brand-new pump.fun / bonk token launches for a few seconds (PumpPortal stream).",
    {"seconds": {"type": "number", "default": 15}, "limit": {"type": "integer", "default": 15}},
    external=True,
    mainnet_only=True,
)
async def new_launches(env, seconds: float = 15, limit: int = 15):
    tokens = await env.pump.new_tokens(min(seconds, 60), min(limit, 50))
    return ok(count=len(tokens), tokens=tokens)
