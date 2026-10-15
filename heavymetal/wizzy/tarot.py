"""Wallet tarot: three cards (past, present, future) chosen in code from a wallet's history and holdings.

Every card has a deterministic trigger and carries the numbers that triggered it. The writer only narrates the
chosen cards. Ties are broken by a hash of the wallet and the UTC date, so a wallet's reading is stable for a day.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import time
from dataclasses import dataclass, field

from heavymetal.signals.audit import audit_mint
from heavymetal.solana.constants import SOL_MINT
from heavymetal.solana.txsummary import summarize_tx
from heavymetal.wizzy.build import build_wallet_facts
from heavymetal.wizzy.omen import ESTABLISHED, omen_for

STABLE_OR_MAJOR = ESTABLISHED


@dataclass
class Card:
    name: str
    glyph: str
    slot: str  # past | present | future
    meaning: str
    score: float
    numbers: dict = field(default_factory=dict)

    def as_fact(self) -> dict:
        return {"card": self.name, "glyph": self.glyph, "meaning": self.meaning, "numbers": self.numbers}


# ---------------------------------------------------------------------- history
async def wallet_history(env, address: str, max_sigs: int = 40) -> tuple[list[dict], str]:
    helius = getattr(env, "helius", None)
    if helius is not None and helius.enabled:
        try:
            return await helius.wallet_swaps(address, max_sigs), "helius"
        except Exception:  # noqa: BLE001 - fall back to RPC
            pass
    sigs = await env.rpc.signatures(address, max_sigs)
    sem = asyncio.Semaphore(5)

    async def fetch(s):
        async with sem:
            try:
                return await env.rpc.transaction(s["signature"])
            except Exception:  # noqa: BLE001
                return None

    txs = await asyncio.gather(*(fetch(s) for s in sigs[:max_sigs]))
    return [summarize_tx(t, address) for t in txs if t], "rpc"


def history_stats(trades: list[dict], held_mints: set[str]) -> dict:
    txs = [t for t in trades if not t.get("failed")]
    trades = [t for t in txs if t["kind"] in ("buy", "sell", "swap")]
    buys = [t for t in trades if t["kind"] == "buy"]
    sells = [t for t in trades if t["kind"] == "sell"]
    first_buy: dict[str, float] = {}
    first_sell: dict[str, float] = {}
    bought, sold = set(), set()
    for t in sorted(trades, key=lambda t: t.get("time") or 0):
        for m, d in (t.get("token_deltas") or {}).items():
            if d > 0:
                bought.add(m)
                first_buy.setdefault(m, t.get("time") or 0)
            elif d < 0:
                sold.add(m)
                first_sell.setdefault(m, t.get("time") or 0)
    flips = sum(1 for m in bought & sold if m in first_sell and 0 <= first_sell[m] - first_buy.get(m, 0) < 3600)
    stamps = [t["time"] for t in trades if t.get("time")]
    span_days = round(max((max(stamps) - min(stamps)) / 86400, 1 / 24), 2) if len(stamps) >= 2 else None
    spent = [-(t["sol_delta"] or 0) for t in buys if (t.get("sol_delta") or 0) < 0]
    traded = bought | sold
    return {
        "transactions": len(txs),
        "trades": len(trades),
        "buys": len(buys),
        "sells": len(sells),
        "mintsTraded": len(traded),
        "roundTrips": len(bought & sold),
        "flipsUnder1h": flips,
        "soldOutMints": len([m for m in traded if m not in held_mints]),
        "spanDays": span_days,
        "tradesPerDay": round(len(trades) / span_days, 2) if span_days else None,
        "avgSolPerBuy": round(sum(spent) / len(spent), 4) if spent else None,
        "solIn": round(sum(t["sol_delta"] for t in trades if (t.get("sol_delta") or 0) > 0), 4),
        "solOut": round(-sum(t["sol_delta"] for t in trades if (t.get("sol_delta") or 0) < 0), 4),
    }


# ---------------------------------------------------------------------- the deck
def past_cards(s: dict) -> list[Card]:
    out = []
    if s["trades"] == 0:
        return out
    if s["mintsTraded"] >= 3 and s["soldOutMints"] / s["mintsTraded"] >= 0.6:
        out.append(
            Card(
                "Death",
                "💀",
                "past",
                "many positions ended; old spells sold to dust",
                s["soldOutMints"] / s["mintsTraded"],
                {"soldOutMints": s["soldOutMints"], "mintsTraded": s["mintsTraded"]},
            )
        )
    if s["flipsUnder1h"] >= 3 or (s["tradesPerDay"] or 0) >= 10:
        out.append(
            Card(
                "Wheel of Fortune",
                "☸",
                "past",
                "fast hands; the wheel spun often",
                min(1.0, max(s["flipsUnder1h"] / 6, (s["tradesPerDay"] or 0) / 20)),
                {"flipsUnder1h": s["flipsUnder1h"], "tradesPerDay": s["tradesPerDay"]},
            )
        )
    if s["buys"] >= 5 and s["avgSolPerBuy"] is not None and s["avgSolPerBuy"] < 0.2:
        out.append(
            Card(
                "The Fool",
                "🃏",
                "past",
                "many small, fresh leaps into new tokens",
                min(1.0, s["buys"] / 15),
                {"buys": s["buys"], "avgSolPerBuy": s["avgSolPerBuy"]},
            )
        )
    if s["tradesPerDay"] is not None and s["tradesPerDay"] < 1:
        out.append(
            Card(
                "Temperance",
                "⚖",
                "past",
                "a patient hand; few trades over many days",
                0.5,
                {"trades": s["trades"], "spanDays": s["spanDays"]},
            )
        )
    return out


def present_cards(w) -> list[Card]:
    out = []
    if not w or not w.totalUsd:
        return out
    top = w.topHoldings[0] if w.topHoldings else None
    sol_usd = (w.solBalance or 0) * (w.solUsdPrice or 0)
    sol_share = min(100.0, round(100 * sol_usd / w.totalUsd, 2)) if w.totalUsd else None
    if top and top.sharePct and top.sharePct > 60:
        out.append(
            Card(
                "The Hermit",
                "🏮",
                "present",
                "one token carries nearly the whole bag",
                top.sharePct / 100,
                {"symbol": top.symbol, "sharePct": top.sharePct},
            )
        )
    if w.tokenCount >= 5 and top and top.sharePct is not None and top.sharePct < 30:
        out.append(
            Card(
                "Temperance",
                "⚖",
                "present",
                "a spread of many small familiars",
                0.6,
                {"tokenCount": w.tokenCount, "topSharePct": top.sharePct},
            )
        )
    if sol_share is not None and sol_share > 50:
        out.append(
            Card(
                "The Emperor",
                "👑",
                "present",
                "mostly SOL; a guarded treasury",
                sol_share / 100,
                {"solSharePct": sol_share, "solBalance": w.solBalance},
            )
        )
    unpriced = [h for h in w.topHoldings if h.usd is None]
    if w.topHoldings and len(unpriced) / len(w.topHoldings) >= 0.5:
        out.append(
            Card(
                "The Hanged Man",
                "🙃",
                "present",
                "many tokens the market can't price",
                0.55,
                {"unpriced": len(unpriced), "shown": len(w.topHoldings)},
            )
        )
    return out


def future_cards(omens: list[dict]) -> list[Card]:
    out = []
    bad = [o for o in omens if o["omen"] in ("cursed", "hexed")]
    if bad:
        worst = max(bad, key=lambda o: o.get("sharePct") or 0)
        out.append(
            Card(
                "The Tower",
                "🗼",
                "future",
                "a held token bears a dark omen",
                0.7 + min(0.3, len(bad) / 10),
                {"symbol": worst["symbol"], "omen": worst["omen"], "sharePct": worst.get("sharePct")},
            )
        )
    rising = [o for o in omens if (o.get("change24hPct") or 0) >= 20]
    if rising:
        best = max(rising, key=lambda o: o["change24hPct"])
        out.append(
            Card(
                "The Star",
                "⭐",
                "future",
                "a held token is rising",
                min(1.0, best["change24hPct"] / 100),
                {"symbol": best["symbol"], "change24hPct": best["change24hPct"]},
            )
        )
    if omens and all(o["omen"] in ("blessed", "murky") for o in omens) and any(o["omen"] == "blessed" for o in omens):
        out.append(
            Card(
                "The Sun",
                "☀",
                "future",
                "the held tokens read clean",
                0.5,
                {"blessed": sum(o["omen"] == "blessed" for o in omens), "read": len(omens)},
            )
        )
    return out


MOON = {
    "past": Card("The Moon", "🌙", "past", "the past is veiled; no clear pattern in the recent trail", 0.0),
    "present": Card("The Moon", "🌙", "present", "the bag is veiled; little the runes can price", 0.0),
    "future": Card("The Moon", "🌙", "future", "the road ahead is misted; nothing to read", 0.0),
}


def seed(address: str, day: str | None = None) -> int:
    day = day or dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
    return int(hashlib.sha256(f"{address}:{day}".encode()).hexdigest()[:8], 16)


def pick(cands: list[Card], slot: str, s: int) -> Card:
    if not cands:
        return MOON[slot]
    best = max(c.score for c in cands)
    top = sorted([c for c in cands if abs(c.score - best) < 1e-9], key=lambda c: c.name)
    return top[s % len(top)]


async def holding_omens(env, w, limit: int = 3) -> list[dict]:
    rows = [h for h in (w.topHoldings if w else []) if h.mint not in STABLE_OR_MAJOR and (h.usd or 0) >= 1][:limit]

    async def one(h):
        try:
            a = await audit_mint(env, h.mint, h.symbol, light=True)
        except Exception:  # noqa: BLE001
            return None
        reasons = a.get("reasons") or []
        return {
            "mint": h.mint,
            "symbol": h.symbol,
            "sharePct": h.sharePct,
            "omen": omen_for(h.mint, a.get("verdict_key"), reasons).kind,
            "change24hPct": (a.get("market") or {}).get("price_change_h24"),
        }

    return [o for o in await asyncio.gather(*(one(h) for h in rows)) if o]


async def build_tarot_facts(env, subject, max_sigs: int = 40, day: str | None = None):
    facts = await build_wallet_facts(env, subject)
    w = facts.wallet
    held = {h.mint for h in (w.topHoldings if w else [])} | ({SOL_MINT} if w and w.solBalance else set())
    try:
        trades, source = await wallet_history(env, subject.key, max_sigs)
    except Exception:  # noqa: BLE001
        trades, source = [], None
        facts.unknowns.append("trade history")
    stats = history_stats(trades, held)
    omens = await holding_omens(env, w)
    s = seed(subject.key, day)
    cards = {
        "past": pick(past_cards(stats), "past", s),
        "present": pick(present_cards(w), "present", s >> 3),
        "future": pick(future_cards(omens), "future", s >> 6),
    }
    if stats["trades"] == 0:
        facts.unknowns.append("no recent swaps found in the scanned history")
    facts.extra = {
        "tarot": {k: c.as_fact() for k, c in cards.items()},
        "history": {**stats, "source": source, "scanned": len(trades), "asOf": time.time()},
        "heldOmens": omens,
    }
    return facts, cards


TAROT_INSTRUCTIONS = (
    "This is a wallet TAROT reading. Narrate the three cards in FACTS.extra.tarot in order: past, present, future. "
    "Name each card with its glyph, give its meaning in your own cryptic words, and cite only the numbers attached "
    "to that card (and FACTS.extra.history if helpful). No predictions of price; the Future card reads risk and "
    "momentum of what is held, nothing more. Scroll sections: The Past, The Present, The Future, Unknowns."
)


def template(facts) -> tuple[str, str, str]:
    t = facts.extra["tarot"]
    lines = [f"{t[k]['glyph']} {k.title()}: {t[k]['card']}: {t[k]['meaning']}." for k in ("past", "present", "future")]
    body = []
    for k in ("past", "present", "future"):
        nums = ", ".join(f"{a}: {b}" for a, b in t[k]["numbers"].items())
        body += [f"## The {k.title()}", f"- {t[k]['glyph']} {t[k]['card']}: {t[k]['meaning']}"]
        if nums:
            body.append(f"- {nums}")
    body += ["## Unknowns", *([f"- The mist hides: {u}" for u in facts.unknowns] or ["- Nothing hidden."])]
    return " ".join(lines), "Three cards for a wallet", "\n".join(body)


# ---------------------------------------------------------------------- pipeline and surfaces
async def tarot_read(ctx, text: str, *, user_id: int | None, surface: str):
    """Tarot reading for a wallet in text. Returns (Written, slug, url, cards)."""
    from heavymetal.wizzy import scrolls
    from heavymetal.wizzy.reading import llm_allowed
    from heavymetal.wizzy.resolve import ResolveError, resolve_subject
    from heavymetal.wizzy.writer import write

    rid = ctx.wdb.add_request(user_id, surface, text, "tarot")
    t0 = time.time()
    async with ctx.readings_sem:
        subject = await resolve_subject(ctx.env, text)
        if subject.kind != "wallet":
            ctx.wdb.finish_request(rid, "unresolved")
            raise ResolveError("tarot reads wallets, and that address is a token")
        sid = ctx.wdb.subject("wallet", subject.key)
        prev = scrolls.recent_for_subject(ctx.wdb, sid, "tarot", ctx.wcfg.dedupe_ca_minutes * 60)
        if prev is not None:
            ctx.wdb.finish_request(rid, "reused", sid)
            return prev, scrolls.public_url(ctx.wcfg.base_url, prev.slug), True
        facts, cards = await build_tarot_facts(ctx.env, subject, ctx.wcfg.tarot_max_signatures)
        written = await write(
            ctx.writer if llm_allowed(ctx) else None,
            facts,
            effort=ctx.wcfg.writer_effort,
            instructions=TAROT_INSTRUCTIONS,
            template_fn=template,
        )
        meta = {"cards": [{"slot": k, "name": c.name, "glyph": c.glyph} for k, c in cards.items()]}
        slug = scrolls.save(
            ctx.wdb,
            label="tarot",
            kind="tarot",
            title=written.title,
            reading=written.reading,
            body_md=written.body,
            omen=None,
            subject_id=sid,
            request_id=rid,
            price_usdc=ctx.wcfg.scroll_price_usdc,
            meta=meta,
        )
    ctx.wdb.finish_request(
        rid, "templated" if written.templated else "ok", sid, written.cost_usd, int((time.time() - t0) * 1000)
    )
    return scrolls.get(ctx.wdb, slug), scrolls.public_url(ctx.wcfg.base_url, slug), False


async def tarot_reply(ctx, user_id: int, text: str, surface: str):
    from heavymetal.wizzy import limits
    from heavymetal.wizzy.bots.core import Button, Reply
    from heavymetal.wizzy.resolve import ResolveError

    v = limits.check_reading(ctx, user_id, surface)
    if not v.allowed:
        return Reply("limited", text=f"The cards need rest. Try again in about {max(1, v.retry_after_s // 60)} min.")
    try:
        scroll, url, _cached = await tarot_read(ctx, text, user_id=user_id, surface=surface)
    except ResolveError as e:
        return Reply("error", text=f"The mists hide that: {e}. Send /tarot <wallet address>.")
    return Reply("reading", scroll.title, scroll.reading, url=url, buttons=[Button("📜 Full scroll", url=url)])


def register() -> None:
    from heavymetal.wizzy.bots import core, tg

    async def intent(ctx, user_id, it, surface):
        return await tarot_reply(ctx, user_id, it.arg, surface)

    async def command(ctx, message, args):
        from heavymetal.wizzy.bots.core import Reply

        if not args.strip():
            return Reply("error", text="Usage: /tarot <wallet address>")
        uid = ctx.wdb.user(tg_id=str(message.from_user.id))["id"]
        return await tarot_reply(ctx, uid, args, "tg")

    core.EXTRA_INTENTS["tarot"] = intent
    tg.EXTRA_COMMANDS["tarot"] = command
    tg.EXTRA_HELP.append("\n/tarot &lt;wallet&gt; · three cards for a wallet")
