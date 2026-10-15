"""Output guard: every number, address, link and $TICKER in the writer's text must come from Facts.

PDF section 8: "every number in the output must appear in Facts, otherwise regenerate". Extended to addresses,
URLs and cashtags so injected text in a token name ("visit scam.xyz") can never reach users.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from heavymetal.solana.fake_check import CANONICAL_MINTS

NUM_RE = re.compile(r"(?<![\w.])\$?(-?\d[\d,]*(?:\.\d+)?)\s*([kmb]|bn|%)?(?![\w])", re.I)
ADDR_RE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")
URL_RE = re.compile(
    r"(https?://[^\s)\]]+|www\.[^\s)\]]+|\b[\w-]+\.(?:com|xyz|io|fun|net|org|app|gg|co|ai|me|so|lol|vip)\b)", re.I
)
CASHTAG_RE = re.compile(r"\$([A-Za-z][A-Za-z0-9_]{0,14})\b")
# Time spans and fixed phrases are not claims about the token.
SAFE_PHRASES = re.compile(
    r"\b(?:\d{1,3}\s?(?:h|hr|hrs|hours?|d|days?|w|weeks?|min|mins|minutes?)|top[\s-]?\d{1,2}|"
    r"24/7|web3|x402|l[12]|nfa|dyor)\b",
    re.I,
)
SMALL_INT_MAX = 10  # "three cards", "2 warnings": small counts are prose, not data
MULT = {"k": 1e3, "m": 1e6, "b": 1e9, "bn": 1e9}
ALWAYS_TICKERS = set(CANONICAL_MINTS)


@dataclass
class Allowed:
    numbers: list[float] = field(default_factory=list)
    strings: set[str] = field(default_factory=set)
    tickers: set[str] = field(default_factory=set)
    urls: set[str] = field(default_factory=set)


def _walk(obj, out: Allowed) -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        v = float(obj)
        if math.isfinite(v):
            out.numbers.append(v)
            if 0 < abs(v) <= 1:
                out.numbers.append(v * 100)  # ratios may be written as percents
            if v > 1000:
                out.numbers.append(round(v))
        return
    if isinstance(obj, str):
        out.strings.add(obj)
        for m in NUM_RE.finditer(obj):  # numbers inside code-written reasons ("Top 10 hold 12.3%")
            parsed = _parse(m)
            if parsed is not None:
                out.numbers.append(parsed[0])
        for m in URL_RE.finditer(obj):
            out.urls.add(m.group(0).lower().rstrip(".,"))
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("symbol",) and isinstance(v, str):
                out.tickers.add(v.upper())
            _walk(v, out)
        return
    if isinstance(obj, (list, tuple, set)):
        for v in obj:
            _walk(v, out)


def allowed_from(facts: dict, extra_urls: list[str] | None = None) -> Allowed:
    a = Allowed()
    trusted = {k: v for k, v in facts.items() if k != "untrusted"}  # creator text can't authorize values
    _walk(trusted, a)
    a.tickers |= ALWAYS_TICKERS
    a.urls |= {u.lower() for u in extra_urls or []}
    return a


def _parse(m: re.Match) -> tuple[float, int, str] | None:
    raw, suffix = m.group(1), (m.group(2) or "").lower()
    try:
        v = float(raw.replace(",", ""))
    except ValueError:
        return None
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    return v * MULT.get(suffix, 1), decimals, suffix


def _number_ok(v: float, decimals: int, suffix: str, allowed: list[float]) -> bool:
    if suffix != "%" and float(v).is_integer() and 0 <= abs(v) <= SMALL_INT_MAX:
        return True
    unit = MULT.get(suffix, 1)
    half = 0.5 * 10 ** (-decimals) * unit  # rounding slack implied by how the number was written
    for a in allowed:
        tol = max(half, 0.006 * abs(a))
        if abs(abs(v) - abs(a)) <= tol:
            return True
    return False


def check(text: str, allowed: Allowed) -> list[str]:
    """Problems found in text; empty means it passes."""
    problems: list[str] = []
    for m in URL_RE.finditer(text):
        u = m.group(0).lower().rstrip(".,")
        if not any(u.startswith(a) or a.startswith(u) for a in allowed.urls):
            problems.append(f"link not in FACTS: {m.group(0)}")
    scrubbed = URL_RE.sub(" ", text)
    for m in ADDR_RE.finditer(scrubbed):
        if m.group(0) not in allowed.strings and not any(m.group(0) in s for s in allowed.strings):
            problems.append(f"address not in FACTS: {m.group(0)}")
    scrubbed = ADDR_RE.sub(" ", scrubbed)
    for m in CASHTAG_RE.finditer(scrubbed):
        if m.group(1).upper() not in allowed.tickers:
            problems.append(f"ticker not in FACTS: ${m.group(1)}")
    scrubbed = SAFE_PHRASES.sub(" ", CASHTAG_RE.sub(" ", scrubbed))
    for m in NUM_RE.finditer(scrubbed):
        parsed = _parse(m)
        if parsed is None:
            continue
        v, decimals, suffix = parsed
        if not _number_ok(v, decimals, suffix, allowed.numbers):
            problems.append(f"number not in FACTS: {m.group(0).strip()}")
    return problems
