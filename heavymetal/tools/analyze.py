"""Market + safety analysis: Dexscreener, RugCheck, on-chain mint/holder data, pump.fun launch stream."""

from __future__ import annotations

import asyncio

from heavymetal.solana.constants import is_valid_pubkey
from heavymetal.solana.fake_check import inspect_token_safety
from heavymetal.solana.resolver import resolve_target
from heavymetal.tools.registry import err, ok, tool

MINT = {"mint": {"type": "string", "description": "token mint address"}}


@tool(
    "token_audit",
    "Comprehensive token audit: resolves DexScreener/pump.fun links, analyzes liquidity, "
    "volume buy/sell ratios, contract traps, fake/copycat spoofing, top holders, and generates a Bubblemaps link.",
    {"target": {"type": "string", "description": "DexScreener URL, pump.fun URL, or token/pair address"}},
    ["target"],
    external=True,
)
async def token_audit(env, target: str):
    try:
        resolved = await resolve_target(env, target)
    except Exception as e:  # noqa: BLE001
        return err(f"failed to resolve target '{target}': {e}")

    mint = resolved.mint
    pairs_fut = env.dex.token_pairs(mint)
    chain_fut = env.rpc.mint_info(mint)
    holders_fut = env.rpc.largest_holders(mint)
    rug_fut = env.rug.summary(mint)

    pairs, chain, holders_data, rug_summary = await asyncio.gather(
        pairs_fut, chain_fut, holders_fut, rug_fut, return_exceptions=True
    )

    top_pair = pairs[0] if isinstance(pairs, list) and pairs else None
    sym = top_pair["base"].get("symbol") if top_pair and top_pair.get("base") else resolved.symbol

    # Run deterministic fake & extension check
    fake_res = await inspect_token_safety(env, mint, sym)

    # Market metrics
    market: dict = {}
    if top_pair:
        tx_h1 = top_pair.get("txns_h1") or {}
        buys_h1 = tx_h1.get("buys") or 0
        sells_h1 = tx_h1.get("sells") or 0
        tot_h1 = buys_h1 + sells_h1
        buy_ratio_h1 = round(buys_h1 / tot_h1, 3) if tot_h1 > 0 else None

        market = {
            "symbol": sym,
            "name": top_pair["base"].get("name") if top_pair.get("base") else resolved.name,
            "price_usd": top_pair.get("price_usd"),
            "liquidity_usd": top_pair.get("liquidity_usd"),
            "fdv": top_pair.get("fdv"),
            "market_cap": top_pair.get("market_cap"),
            "age_hours": top_pair.get("age_hours"),
            "volume_h1": (top_pair.get("volume") or {}).get("h1"),
            "volume_h24": (top_pair.get("volume") or {}).get("h24"),
            "price_change_h1": (top_pair.get("price_change") or {}).get("h1"),
            "price_change_h24": (top_pair.get("price_change") or {}).get("h24"),
            "buys_h1": buys_h1,
            "sells_h1": sells_h1,
            "buy_ratio_h1": buy_ratio_h1,
            "dex": top_pair.get("dex"),
            "pair": top_pair.get("pair"),
            "socials": top_pair.get("socials", []),
            "url": top_pair.get("url"),
        }

    # Holder distribution
    supply = chain["supply"] if not isinstance(chain, Exception) and chain.get("supply") else 1
    top_holders = []
    top10_pct = None
    if isinstance(holders_data, list):
        top_holders = [
            {"account": h["account"], "pct": round(100 * h["amount"] / supply, 2)} for h in holders_data[:10]
        ]
        top10_pct = round(sum(h["pct"] for h in top_holders), 2)

    # Safety metrics
    freeze_auth = chain.get("freeze_authority") if not isinstance(chain, Exception) else None
    mint_auth = chain.get("mint_authority") if not isinstance(chain, Exception) else None
    lp_locked = rug_summary.get("lp_locked_pct") if not isinstance(rug_summary, Exception) else None
    rug_score = rug_summary.get("score_normalised") if not isinstance(rug_summary, Exception) else None

    # Verdict synthesis
    reasons = []
    if fake_res.is_fake:
        verdict = "HARD PASS / FAKE TOKEN"
        reasons += fake_res.reasons
    elif freeze_auth:
        verdict = "HARD PASS / HONEYPOT"
        reasons.append(f"Freeze authority is active ({freeze_auth[:8]}…)")
    elif rug_score and rug_score > 60:
        verdict = "HARD PASS / HIGH RISK"
        reasons.append(f"RugCheck risk score is critical: {rug_score}/100")
    else:
        # Check positive market momentum
        positives = []
        if freeze_auth is None:
            positives.append("Freeze authority revoked")
        if mint_auth is None:
            positives.append("Mint authority revoked")
        if lp_locked and lp_locked > 80:
            positives.append(f"LP {lp_locked}% locked")
        if top10_pct and top10_pct < 30:
            positives.append(f"Top 10 hold only {top10_pct}% (healthy distribution)")
        if market.get("buy_ratio_h1") and market["buy_ratio_h1"] > 0.65:
            positives.append(f"Strong buy pressure ({int(market['buy_ratio_h1'] * 100)}% buys)")

        if market.get("liquidity_usd", 0) >= 15_000 and len(positives) >= 3 and not fake_res.warnings:
            verdict = "HIGH CONVICTION (BULLISH)"
            reasons = positives
        else:
            verdict = "SPECULATIVE"
            reasons = positives + fake_res.warnings

    bubblemaps_url = f"https://app.bubblemaps.io/sol/token/{mint}"

    return ok(
        mint=mint,
        resolved=resolved.to_dict(),
        verdict=verdict,
        reasons=reasons,
        warnings=fake_res.warnings,
        market=market,
        safety={
            "mint_authority": mint_auth,
            "freeze_authority": freeze_auth,
            "lp_locked_pct": lp_locked,
            "rug_score_normalised": rug_score,
            "is_token_2022": fake_res.is_token_2022,
            "transfer_fee_bps": fake_res.transfer_fee_bps,
        },
        holders={
            "top10_pct": top10_pct,
            "top_accounts": top_holders[:5],
        },
        bubblemaps_url=bubblemaps_url,
    )


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
