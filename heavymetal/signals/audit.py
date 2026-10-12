"""Code-only token audit: the verdict logic behind `token_audit`, shared with the background scanner.

No LLM calls. Verdict order: FAKE -> HONEYPOT -> FARM -> HIGH_RISK -> HIGH_CONVICTION | SPECULATIVE.
"""

from __future__ import annotations

import asyncio
import time

from heavymetal.signals.farm import FarmResult, farm_check

VERDICT_TEXT = {
    "FAKE": "HARD PASS / FAKE TOKEN",
    "HONEYPOT": "HARD PASS / HONEYPOT",
    "FARM": "HARD PASS / FARM",
    "HIGH_RISK": "HARD PASS / HIGH RISK",
    "HIGH_CONVICTION": "HIGH CONVICTION (BULLISH)",
    "SPECULATIVE": "SPECULATIVE",
}
HARD_PASS = {"FAKE", "HONEYPOT", "FARM", "HIGH_RISK"}
FEATURE_VERSION = 1


async def _safe(coro):
    try:
        return await coro
    except Exception as e:  # noqa: BLE001
        return e


def _ok(x):
    return x is not None and not isinstance(x, Exception)


async def audit_mint(env, mint: str, symbol_hint: str | None = None, light: bool = False) -> dict:
    """Audit one mint. light=True skips the holder scan (used by the scanner to spare the RPC)."""
    from heavymetal.solana.fake_check import inspect_token_safety

    async def none():
        return None

    pairs, chain, holders_data, rug = await asyncio.gather(
        _safe(env.dex.token_pairs(mint)),
        _safe(env.rpc.mint_info(mint)),
        none() if light else _safe(env.rpc.largest_holders(mint)),
        _safe(env.rug.summary(mint)),
    )
    top_pair = pairs[0] if _ok(pairs) and pairs else None
    sym = (top_pair or {}).get("base", {}).get("symbol") or symbol_hint
    fake_res, farm = await asyncio.gather(
        inspect_token_safety(env, mint, sym),
        farm_check(env, mint, top_pair, deep=not light),
    )
    if isinstance(farm, Exception):  # pragma: no cover - farm_check never raises
        farm = FarmResult()

    market: dict = {}
    if top_pair:
        tx_h1 = top_pair.get("txns_h1") or {}
        buys_h1, sells_h1 = tx_h1.get("buys") or 0, tx_h1.get("sells") or 0
        tot_h1 = buys_h1 + sells_h1
        market = {
            "symbol": sym,
            "name": (top_pair.get("base") or {}).get("name"),
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
            "buy_ratio_h1": round(buys_h1 / tot_h1, 3) if tot_h1 > 0 else None,
            "dex": top_pair.get("dex"),
            "pair": top_pair.get("pair"),
            "socials": top_pair.get("socials", []),
            "url": top_pair.get("url"),
            "boosts": top_pair.get("boosts"),
        }

    fm = farm.metrics or {}
    if fm.get("pool") and (not market.get("liquidity_usd") or not (market.get("fdv") or market.get("market_cap"))):
        # Dexscreener's top pair can be a stale curve pair with no liquidity: fill from GeckoTerminal's best pool
        market.update(
            {
                "symbol": market.get("symbol") or fm.get("symbol") or sym,
                "price_usd": fm.get("price_usd") or market.get("price_usd"),
                "liquidity_usd": fm.get("liquidity_usd"),
                "fdv": fm.get("fdv") or market.get("fdv"),
                "volume_h24": fm.get("volume_h24") or market.get("volume_h24"),
                "price_change_h24": fm.get("price_change_h24")
                if fm.get("price_change_h24") is not None
                else market.get("price_change_h24"),
                "age_hours": market.get("age_hours") or fm.get("age_hours"),
                "dex": fm.get("dex") or market.get("dex"),
                "pair": fm.get("pool"),
                "filled_from": "geckoterminal",
            }
        )

    supply = chain["supply"] if _ok(chain) and chain.get("supply") else 1
    top_holders, top10_pct = [], None
    if _ok(holders_data) and isinstance(holders_data, list):
        top_holders = [
            {"account": h["account"], "pct": round(100 * h["amount"] / supply, 2)} for h in holders_data[:10]
        ]
        top10_pct = round(sum(h["pct"] for h in top_holders), 2)

    freeze_auth = chain.get("freeze_authority") if _ok(chain) else None
    mint_auth = chain.get("mint_authority") if _ok(chain) else None
    lp_locked = rug.get("lp_locked_pct") if _ok(rug) else None
    rug_score = rug.get("score_normalised") if _ok(rug) else None

    reasons: list[str] = []
    if fake_res.is_fake:
        key = "FAKE"
        reasons += fake_res.reasons
    elif freeze_auth:
        key = "HONEYPOT"
        reasons.append(f"Freeze authority is active ({freeze_auth[:8]}…)")
    elif farm.is_farm:
        key = "FARM"
        reasons += [f"farm ({farm.kind}): {r}" for r in farm.reasons]
    elif rug_score and rug_score > 60:
        key = "HIGH_RISK"
        reasons.append(f"RugCheck risk score is critical: {rug_score}/100")
    else:
        positives = []
        if _ok(chain) and freeze_auth is None:
            positives.append("Freeze authority revoked")
        if _ok(chain) and mint_auth is None:
            positives.append("Mint authority revoked")
        if lp_locked and lp_locked > 80:
            positives.append(f"LP {lp_locked}% locked")
        if top10_pct and top10_pct < 30:
            positives.append(f"Top 10 hold only {top10_pct}% (healthy distribution)")
        if market.get("buy_ratio_h1") and market["buy_ratio_h1"] > 0.65:
            positives.append(f"Strong buy pressure ({int(market['buy_ratio_h1'] * 100)}% buys)")
        clean = not fake_res.warnings and not farm.warnings
        if (market.get("liquidity_usd") or 0) >= 15_000 and len(positives) >= 3 and clean:
            key = "HIGH_CONVICTION"
            reasons = positives
        else:
            key = "SPECULATIVE"
            reasons = positives + fake_res.warnings + farm.warnings

    features = {
        "as_of": time.time(),
        "v": FEATURE_VERSION,
        "liquidity_usd": market.get("liquidity_usd"),
        "fdv": market.get("fdv"),
        "age_hours": market.get("age_hours"),
        "volume_h1": market.get("volume_h1"),
        "volume_h24": market.get("volume_h24"),
        "price_change_h1": market.get("price_change_h1"),
        "price_change_h24": market.get("price_change_h24"),
        "buy_ratio_h1": market.get("buy_ratio_h1"),
        "buys_h1": market.get("buys_h1"),
        "sells_h1": market.get("sells_h1"),
        "top10_pct": top10_pct,
        "rug_score": rug_score,
        "lp_locked_pct": lp_locked,
        "mint_auth_active": bool(mint_auth) if _ok(chain) else None,
        "freeze_active": bool(freeze_auth) if _ok(chain) else None,
        "is_token_2022": fake_res.is_token_2022,
        "turnover": fm.get("turnover"),
        "swaps_per_wallet": fm.get("swaps_per_wallet"),
        "wallets_h24": fm.get("wallets_h24"),
        "farm_warnings": len(farm.warnings),
        "fake_warnings": len(fake_res.warnings),
        "n_socials": len(market.get("socials") or []),
        "boosts": market.get("boosts"),
        "dex": market.get("dex"),
    }
    return {
        "mint": mint,
        "verdict": VERDICT_TEXT[key],
        "verdict_key": key,
        "reasons": reasons,
        "warnings": fake_res.warnings + farm.warnings,
        "market": market,
        "safety": {
            "mint_authority": mint_auth,
            "freeze_authority": freeze_auth,
            "lp_locked_pct": lp_locked,
            "rug_score_normalised": rug_score,
            "is_token_2022": fake_res.is_token_2022,
            "transfer_fee_bps": fake_res.transfer_fee_bps,
        },
        "farm": {
            "is_farm": farm.is_farm,
            "kind": farm.kind,
            "reasons": farm.reasons,
            "warnings": farm.warnings,
            "metrics": {
                k: fm.get(k)
                for k in (
                    "turnover",
                    "swaps_per_wallet",
                    "swaps_per_wallet_source",
                    "wallets_h24",
                    "wallets_source",
                    "sources",
                )
            },
        },
        "holders": {"top10_pct": top10_pct, "top_accounts": top_holders[:5]},
        "features": features,
        "bubblemaps_url": f"https://app.bubblemaps.io/sol/token/{mint}",
    }
