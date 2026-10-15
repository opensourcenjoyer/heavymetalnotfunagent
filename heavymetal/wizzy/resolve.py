"""Turn what a user typed into a subject: a token mint or a wallet.

Links, mints and pair addresses go through heavymetal's resolver. Tickers ($BONK or BONK) resolve to the
canonical mint when one exists, otherwise to the most liquid Solana pair whose symbol matches exactly after
homoglyph cleaning. A valid address that is neither a mint nor a pair is a wallet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from heavymetal.solana.constants import is_valid_pubkey
from heavymetal.solana.fake_check import CANONICAL_MINTS, normalize_ticker
from heavymetal.solana.resolver import extract_address_from_text, resolve_target

TICKER_RE = re.compile(r"^\$?([^\W_][\w.\-]{0,14})$")
CASHTAG_RE = re.compile(r"\$([^\W\d_][\w]{0,14})")  # any script: homoglyph tickers are cleaned later


class ResolveError(ValueError):
    """The mists hide this subject (nothing resolvable in the input)."""


@dataclass
class Subject:
    kind: str  # token | wallet
    key: str  # mint or wallet address
    symbol: str | None = None
    name: str | None = None
    raw: str = ""
    notes: list[str] = field(default_factory=list)  # e.g. ambiguity warnings, become Facts.unknowns


def find_ticker(text: str) -> str | None:
    """A ticker in free text: a $CASHTAG anywhere, or the whole input if it is one bare word."""
    m = CASHTAG_RE.search(text)
    if m:
        return m.group(1)
    t = text.strip()
    m = TICKER_RE.match(t)
    if m and len(t) < 32:
        return m.group(1)
    return None


async def resolve_ticker(env, ticker: str) -> Subject:
    norm = normalize_ticker(ticker)
    if not norm:
        raise ResolveError("empty ticker")
    if norm in CANONICAL_MINTS:
        return Subject("token", CANONICAL_MINTS[norm], symbol=norm, raw=ticker)
    try:
        pairs = await env.dex.search(norm, limit=20)
    except Exception as e:
        raise ResolveError(f"ticker search failed: {e}") from e
    matches = [p for p in pairs if normalize_ticker((p.get("base") or {}).get("symbol")) == norm]
    if not matches:
        raise ResolveError(f"no Solana token found for ${norm}")
    best = matches[0]  # search results are sorted by liquidity
    mints = {(p.get("base") or {}).get("address") for p in matches}
    notes = []
    if len(mints) > 1:
        notes.append(f"{len(mints)} tokens share the ticker ${norm}; this reading uses the most liquid one")
    base = best.get("base") or {}
    return Subject("token", base["address"], symbol=base.get("symbol"), name=base.get("name"), raw=ticker, notes=notes)


async def resolve_subject(env, text: str) -> Subject:
    text = (text or "").strip()
    if not text:
        raise ResolveError("nothing to read")
    address, _url = extract_address_from_text(text)
    if address and is_valid_pubkey(address):
        target = await resolve_target(env, address if not _url else text)
        if target.kind in ("mint", "pair"):
            return Subject("token", target.mint, symbol=target.symbol, name=target.name, raw=text)
        return Subject("wallet", address, raw=text)
    ticker = find_ticker(text)
    if ticker:
        return await resolve_ticker(env, ticker)
    raise ResolveError("no token, ticker or wallet found")
