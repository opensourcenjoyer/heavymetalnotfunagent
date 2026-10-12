"""Farm filter: flag tokens whose volume is a farm (wash loops, fee/points farming, inorganic churn).

Farms get flagged the same way rugs do: `token_audit` returns HARD PASS / FARM, the scanner drops
them, Trenches does not count their volume, and the swap review blocks buys in code (FARM_BLOCK).

Gates, in order (thresholds live in cfg.signals):
  manual        mint is on the deny list (known bot loops, relaunches, impostors)
  wash          24h volume > 300x the liquidity it holds: a bot churning an empty book, not a crowd
  zero_reserve  liquidity cannot be read, yet it carries more than $10K per wallet
  roundtrip     wallets average 100+ swaps a day each, anywhere
  feefarm       wallets average 15+ swaps a day through a near-zero-fee pool (exchange volume-points farming)
  thin_crowd    fewer than 25 wallets carrying $50K+ of volume
  flat_loop     turnover > 100x with a flat price and a 50/50 buy/sell split: a loop, not a market
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# DEX ids (GeckoTerminal / Dexscreener) whose pools commonly run near-zero fee tiers.
LOW_FEE_DEXES = {
    "orca",
    "raydium-clmm",
    "meteora",
    "meteora-dlmm",
    "meteoradlmm",
    "lifinity",
    "lifinity-v2",
    "phoenix",
    "manifest",
    "solfi",
    "obric-v2",
    "humidifi",
    "tessera",
    "zerofi",
    "goonfi",
}
LOW_FEE_TIER = 0.0005  # 5 bps or less


@dataclass
class FarmResult:
    is_farm: bool = False
    kind: str | None = None
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _g(d: dict | None, *path, default=None):
    for p in path:
        if not isinstance(d, dict):
            return default
        d = d.get(p)
    return default if d is None else d


def metrics_from(
    gt: dict | None = None,
    pair: dict | None = None,
    birdeye: dict | None = None,
    helius: dict | None = None,
    dune: dict | None = None,
) -> dict:
    """Merge whatever sources we have into one flat dict of farm-relevant metrics."""
    gt, pair, birdeye, helius, dune = gt or {}, pair or {}, birdeye or {}, helius or {}, dune or {}
    m: dict = {
        "mint": gt.get("mint") or _g(pair, "base", "address") or dune.get("mint"),
        "symbol": gt.get("symbol") or _g(pair, "base", "symbol") or dune.get("symbol"),
        "dex": gt.get("dex") or pair.get("dex"),
        "liquidity_usd": gt.get("liquidity_usd") if gt.get("liquidity_usd") is not None else pair.get("liquidity_usd"),
        "volume_h24": _g(gt, "volume", "h24") or _g(pair, "volume", "h24") or dune.get("volume_usd"),
        "price_change_h24": _g(gt, "price_change", "h24")
        if _g(gt, "price_change", "h24") is not None
        else _g(pair, "price_change", "h24"),
        "fdv": gt.get("fdv") or pair.get("fdv"),
        "price_usd": gt.get("price_usd") or pair.get("price_usd"),
        "pool": gt.get("pool") or pair.get("pair"),
        "age_hours": gt.get("age_hours") if gt.get("age_hours") is not None else pair.get("age_hours"),
    }
    tx = _g(gt, "txns", "h24") or {}
    ptx = pair.get("txns_h24") or {}
    m["buys_h24"] = tx.get("buys") or ptx.get("buys")
    m["sells_h24"] = tx.get("sells") or ptx.get("sells")
    swaps = (m["buys_h24"] or 0) + (m["sells_h24"] or 0) or dune.get("swaps") or None
    m["swaps_h24"] = swaps
    # wallets: best source first. buyers+sellers double-counts two-way wallets -> fewer swaps per wallet,
    # which errs on the side of NOT calling a farm.
    wallets, wsrc = None, None
    if birdeye.get("unique_wallets_24h"):
        wallets, wsrc = birdeye["unique_wallets_24h"], "birdeye"
    elif dune.get("traders"):
        wallets, wsrc = dune["traders"], "dune"
    elif tx.get("buyers") or tx.get("sellers"):
        wallets, wsrc = (tx.get("buyers") or 0) + (tx.get("sellers") or 0), "gt"
    m["wallets_h24"], m["wallets_source"] = wallets, wsrc
    spw, ssrc = None, None
    if helius.get("swaps_per_wallet_day") is not None:
        spw, ssrc = helius["swaps_per_wallet_day"], "helius"
    elif birdeye.get("trades_24h") and birdeye.get("unique_wallets_24h"):
        spw, ssrc = birdeye["trades_24h"] / birdeye["unique_wallets_24h"], "birdeye"
    elif swaps and wallets:
        spw, ssrc = swaps / wallets, wsrc
    m["swaps_per_wallet"] = round(spw, 2) if spw is not None else None
    m["swaps_per_wallet_source"] = ssrc
    m["top_wallet_share"] = helius.get("top_wallet_share")
    m["fee_tier"] = dune.get("min_fee_tier")
    liq, vol = m["liquidity_usd"], m["volume_h24"]
    m["turnover"] = round(vol / liq, 1) if liq and vol and liq > 0 else None
    return m


def classify_farm(m: dict, cfg) -> FarmResult:
    """m: output of metrics_from(). cfg: Config (uses cfg.signals)."""
    s = cfg.signals
    r = FarmResult(metrics=m)
    liq, vol = m.get("liquidity_usd"), m.get("volume_h24") or 0
    turnover, spw, wallets = m.get("turnover"), m.get("swaps_per_wallet"), m.get("wallets_h24")
    chg = m.get("price_change_h24")
    low_fee = (m.get("dex") or "").lower() in LOW_FEE_DEXES or (
        m.get("fee_tier") is not None and m["fee_tier"] <= LOW_FEE_TIER
    )

    def flag(kind: str, why: str) -> None:
        if not r.is_farm:
            r.is_farm, r.kind = True, kind
        r.reasons.append(why)

    if m.get("mint") and m["mint"] in set(s.deny_mints):
        flag("manual", "excluded by hand (deny list)")
    if turnover is not None and turnover > s.wash_turnover:
        flag(
            "wash",
            f"24h volume is {turnover:,.0f}x its liquidity (> {s.wash_turnover:g}x): a bot churning an empty book",
        )
    if (liq is None or liq < 1) and vol > 0:
        if wallets and vol / wallets > s.zero_reserve_usd_per_wallet:
            flag(
                "zero_reserve",
                f"liquidity cannot be read, yet ${vol / wallets:,.0f} traded per wallet "
                f"(> ${s.zero_reserve_usd_per_wallet:,.0f})",
            )
        else:
            r.warnings.append("liquidity cannot be read: volume on this pool is unverifiable")
    if spw is not None and spw >= s.roundtrip_swaps_per_wallet:
        flag(
            "roundtrip",
            f"wallets average {spw:.0f} swaps a day each (>= {s.roundtrip_swaps_per_wallet:g}): round-tripping",
        )
    elif spw is not None and spw >= s.feefarm_swaps_per_wallet and low_fee:
        flag(
            "feefarm",
            f"{spw:.0f} swaps a wallet a day through a near-zero-fee pool ({m.get('dex')}): volume-points farming",
        )
    elif spw is not None and spw >= s.feefarm_swaps_per_wallet * 0.66:
        r.warnings.append(f"heavy churn: {spw:.0f} swaps per wallet in 24h ({m.get('swaps_per_wallet_source')})")
    if wallets is not None and wallets < s.min_crowd_wallets and vol >= s.min_crowd_volume:
        flag("thin_crowd", f"${vol:,.0f} of volume from only {int(wallets)} wallets: not a crowd")
    buys, sells = m.get("buys_h24") or 0, m.get("sells_h24") or 0
    if (
        turnover is not None
        and turnover > s.loop_turnover
        and chg is not None
        and abs(chg) < 2
        and buys + sells > 0
        and 0.45 <= buys / (buys + sells) <= 0.55
        and vol >= s.min_crowd_volume
    ):
        flag("flat_loop", f"turnover {turnover:,.0f}x at a flat price ({chg:+.1f}%) with 50/50 flow: a loop")
    if not r.is_farm and turnover is not None and turnover > s.loop_turnover:
        r.warnings.append(f"high turnover: 24h volume is {turnover:,.0f}x liquidity")
    if m.get("top_wallet_share") and m["top_wallet_share"] > 0.3:
        r.warnings.append(f"one wallet made {m['top_wallet_share']:.0%} of recent swaps")
    return r


async def farm_check(env, mint: str, pair: dict | None = None, deep: bool = True) -> FarmResult:
    """Fetch what we can (GeckoTerminal; Birdeye/Helius when keyed) and classify. Never raises."""
    gt = be = he = None
    gecko = getattr(env, "gecko", None)
    if gecko is not None:
        try:
            pools = await gecko.token_pools(mint)
            gt = pools[0] if pools else None
        except Exception:  # noqa: BLE001 - best effort
            gt = None
    if deep:
        birdeye = getattr(env, "birdeye", None)
        if birdeye is not None and birdeye.enabled:
            try:
                be = await birdeye.token_overview(mint)
            except Exception:  # noqa: BLE001
                be = None
        helius = getattr(env, "helius", None)
        pool_addr = (gt or {}).get("pool") or (pair or {}).get("pair")
        if helius is not None and helius.enabled and pool_addr:
            try:
                he = await helius.pool_swaps(pool_addr)
            except Exception:  # noqa: BLE001
                he = None
    m = metrics_from(gt=gt, pair=pair, birdeye=be, helius=he)
    m["mint"] = m.get("mint") or mint
    m["sources"] = [n for n, v in (("geckoterminal", gt), ("dexscreener", pair), ("birdeye", be), ("helius", he)) if v]
    return classify_farm(m, env.cfg)
