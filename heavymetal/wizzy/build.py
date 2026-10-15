"""Build Facts from heavymetal's data clients. Every failed source becomes an unknown; nothing is invented."""

from __future__ import annotations

import asyncio
import re
import time

from heavymetal.signals.audit import HARD_PASS, audit_mint
from heavymetal.solana.fake_check import normalize_ticker
from heavymetal.solana.holdings import holdings
from heavymetal.wizzy.facts import (
    Authorities,
    Facts,
    Farm,
    Holders,
    Holding,
    OhlcvSummary,
    Protocol,
    Source,
    Subject,
    Supply,
    TokenFacts,
    WalletFacts,
)
from heavymetal.wizzy.omen import ESTABLISHED, omen_for
from heavymetal.wizzy.resolve import Subject as Resolved

URL_RE = re.compile(r"(https?://\S+|www\.\S+|\b[\w-]+\.(?:com|xyz|io|fun|net|org|app|gg|co|ai|me|so|lol|vip)\b)", re.I)
MAX_UNTRUSTED = 60
ESTABLISHED_NOTE = (
    "Established token: its issuer keeps mint/freeze authority by design (normal for stablecoins and majors)"
)


def clean_untrusted(s: str | None) -> str:
    """Creator-written text: strip links and hidden characters, clip. Data only, never instructions."""
    if not s:
        return ""
    s = URL_RE.sub("[link removed]", str(s))
    s = re.sub(r"[​-‏⁠-⁤﻿­]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:MAX_UNTRUSTED]


async def _safe(coro):
    try:
        return await coro
    except Exception as e:  # noqa: BLE001
        return e


def r2(v):
    return round(float(v), 2) if isinstance(v, (int, float)) and not isinstance(v, bool) else v


def _ok(x) -> bool:
    return x is not None and not isinstance(x, Exception)


def ohlcv_summary(candles: list[dict], source: str) -> OhlcvSummary:
    """24h summary from hourly candles (oldest first)."""
    c = [k for k in candles if k.get("close") is not None][-24:]
    if not c:
        return OhlcvSummary(source=source)
    first_open = c[0].get("open") or c[0]["close"]
    change = round((c[-1]["close"] / first_open - 1) * 100, 2) if first_open else None
    return OhlcvSummary(
        change24hPct=change,
        high24h=max(k.get("high") or k["close"] for k in c),
        low24h=min(k.get("low") or k["close"] for k in c),
        volume24hUsd=round(sum(k.get("volume") or 0 for k in c), 2),
        candles=len(c),
        source=source,
    )


async def _ohlcv(env, mint: str, pool: str | None) -> tuple[OhlcvSummary, list[dict]]:
    birdeye = getattr(env, "birdeye", None)
    if birdeye is not None and birdeye.enabled:
        try:
            candles = await birdeye.ohlcv_hourly(mint, 24)
            return ohlcv_summary(candles, "birdeye"), candles[-24:]
        except Exception:  # noqa: BLE001 - fall back to GeckoTerminal
            pass
    gecko = getattr(env, "gecko", None)
    if gecko is None:
        raise RuntimeError("no OHLCV source")
    if not pool:
        pools = await gecko.token_pools(mint)
        pool = pools[0]["pool"] if pools else None
    if not pool:
        raise RuntimeError("no pool for OHLCV")
    candles = await gecko.ohlcv(pool, "hour", 1, 24)
    return ohlcv_summary(candles, "geckoterminal"), candles[-24:]


async def _protocol(env, mint: str) -> Protocol | None:
    llama = getattr(env, "llama", None)
    if llama is None:
        return None
    p = await llama.protocol_for_token(mint)
    if not p:
        return None
    fees = None
    try:
        fees = await llama.protocol_fees_24h(p["slug"])
    except Exception:  # noqa: BLE001
        fees = None
    return Protocol(name=p["name"], slug=p["slug"], category=p.get("category"), tvlUsd=p.get("tvl"), fees24hUsd=fees)


async def build_token_facts(env, subject: Resolved, light: bool = False) -> Facts:
    mint = subject.key
    now = time.time()
    audit, chain, report, jup, proto = await asyncio.gather(
        _safe(audit_mint(env, mint, subject.symbol, light=light)),
        _safe(env.rpc.mint_info(mint)),
        _safe(env.rug.report(mint)),
        _safe(env.jup.prices([mint])),
        _safe(_protocol(env, mint)) if not light else asyncio.sleep(0, result=None),
    )
    sources: list[Source] = []
    unknowns: list[str] = list(subject.notes)
    risk: list[str] = []
    strengths: list[str] = []

    def src(name, val):
        sources.append(Source(name=name, fetchedAt=now, ok=_ok(val)))

    src("audit (dexscreener, rpc, rugcheck, farm filter)", audit)
    src("rpc mint account", chain)
    src("rugcheck report", report)
    src("jupiter price", jup)

    a = audit if _ok(audit) else {}
    m = a.get("market") or {}
    safety = a.get("safety") or {}
    farm = a.get("farm") or {}
    if not _ok(audit):
        unknowns.append("market and safety audit unavailable")
    if not m:
        unknowns.append("no trading pair found")

    decimals = chain.get("decimals") if _ok(chain) else None
    total_supply = chain["supply"] / 10**decimals if _ok(chain) and decimals is not None else None
    if not _ok(chain):
        unknowns.append("on-chain mint account unavailable")
    unknowns.append("circulating supply (not derivable on-chain)")

    holders_count = report.get("total_holders") if _ok(report) else None
    top10 = (a.get("holders") or {}).get("top10_pct")
    if top10 is None and _ok(report):
        top10 = report.get("top10_pct")
    if top10 is None:
        unknowns.append("holder concentration")
    if holders_count is None:
        unknowns.append("holder count")

    pool = m.get("pair")
    got = await _safe(_ohlcv(env, mint, pool)) if m else RuntimeError("no market")
    src("ohlcv", got)
    ohlcv, candles = got if _ok(got) else (OhlcvSummary(), [])
    if not ohlcv.candles:
        unknowns.append("24h price history")

    key = a.get("verdict_key")
    reasons = a.get("reasons") or []
    if key in HARD_PASS:
        risk += reasons
    else:
        strengths += reasons
    risk += [w for w in a.get("warnings") or [] if w not in risk]

    auth_active = bool(safety.get("mint_authority") or safety.get("freeze_authority"))
    if mint in ESTABLISHED and auth_active:
        # Regulated stablecoins and majors keep admin authorities by design: say so, without honeypot language.
        risk = [ESTABLISHED_NOTE] + [r for r in risk if "freeze" not in r.lower() and "mint authority" not in r.lower()]

    jprice = jup.get(mint) if _ok(jup) else None
    protocol = proto if _ok(proto) else None
    if light:
        unknowns.append("protocol TVL and fees (skipped in quick readings)")
    else:
        src("defillama protocols", proto)

    sym = normalize_ticker(m.get("symbol") or subject.symbol) or None
    token = TokenFacts(
        mint=mint,
        symbol=sym,
        decimals=decimals,
        priceUsd=m.get("price_usd"),
        jupiterPriceUsd=jprice,
        mcapUsd=m.get("market_cap"),
        fdvUsd=m.get("fdv"),
        liquidityUsd=r2(m.get("liquidity_usd")),
        volume24hUsd=m.get("volume_h24"),
        priceChange24hPct=r2(m.get("price_change_h24")),
        ageHours=round(m["age_hours"], 1) if m.get("age_hours") is not None else None,
        dex=m.get("dex"),
        supply=Supply(total=total_supply),
        authorities=Authorities(
            mint=safety.get("mint_authority") if _ok(audit) else (chain.get("mint_authority") if _ok(chain) else None),
            freeze=safety.get("freeze_authority")
            if _ok(audit)
            else (chain.get("freeze_authority") if _ok(chain) else None),
        ),
        holders=Holders(top10Pct=r2(top10), countApprox=holders_count),
        ohlcvSummary=ohlcv,
        lpLockedPct=r2(safety.get("lp_locked_pct")),
        rugScore=r2(safety.get("rug_score_normalised")),
        farm=Farm(isFarm=bool(farm.get("is_farm")), kind=farm.get("kind")),
        verdictKey=key,
        protocol=protocol,
    )
    token.omen = omen_for(mint, key, risk if key in HARD_PASS else strengths)
    untrusted = {"name": clean_untrusted(m.get("name") or subject.name), "symbol": clean_untrusted(m.get("symbol"))}
    return Facts(
        asOf=now,
        subject=Subject(kind="token", mint=mint, symbol=sym),
        sources=sources,
        token=token,
        strengths=strengths,
        unknowns=unknowns,
        riskFlags=risk,
        untrusted={k: v for k, v in untrusted.items() if v},
        extra={
            "chart": {"ts": [c["ts"] for c in candles], "close": [c["close"] for c in candles], "source": ohlcv.source}
        }
        if candles
        else {},
    )


async def build_wallet_facts(env, subject: Resolved, top: int = 8) -> Facts:
    addr = subject.key
    now = time.time()
    h = await holdings(env, addr)
    symbols: dict[str, str] = {}
    mints = [t["mint"] for t in h["tokens"][:top]]
    unknowns: list[str] = []
    try:
        batch = await env.dex.tokens_batch(mints) if mints else {}
        symbols = {k: normalize_ticker((v.get("base") or {}).get("symbol")) for k, v in batch.items()}
    except Exception:  # noqa: BLE001
        unknowns.append("token symbols")
    total = h.get("total_usd")
    rows = []
    for t in h["tokens"][:top]:
        share = round(100 * t["usd"] / total, 2) if total and t.get("usd") else None
        rows.append(
            Holding(
                mint=t["mint"], symbol=symbols.get(t["mint"]) or None, amount=t["amount"], usd=t["usd"], sharePct=share
            )
        )
    if total is None:
        unknowns.append("USD values (prices unavailable)")
    return Facts(
        asOf=now,
        subject=Subject(kind="wallet", wallet=addr),
        sources=[Source(name="rpc balances + jupiter prices", fetchedAt=now)],
        wallet=WalletFacts(
            address=addr,
            solBalance=h.get("sol"),
            solUsdPrice=h.get("sol_usd_price"),
            totalUsd=total,
            tokenCount=len(h["tokens"]),
            topHoldings=rows,
        ),
        unknowns=unknowns,
    )


async def build_facts(env, subject: Resolved, light: bool = False) -> Facts:
    if subject.kind == "wallet":
        return await build_wallet_facts(env, subject)
    return await build_token_facts(env, subject, light=light)
