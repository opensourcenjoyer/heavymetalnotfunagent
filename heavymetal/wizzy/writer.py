"""Facts-only writer: Claude with structured output, the output guard, and a templated fallback.

The model never sees tools. Its output must pass guard.check (numbers, addresses, links, tickers all from
Facts); otherwise it gets up to MAX_RETRIES corrections, then the reading is built from a code template.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources

from heavymetal.wizzy import guard
from heavymetal.wizzy.facts import Facts
from heavymetal.wizzy.omen import OMEN_GLYPH, OMEN_LINE

FOOTER = "NFA. DYOR. The runes are not financial advice."
MAX_RETRIES = 2
SCHEMA = {
    "type": "object",
    "properties": {
        "reading": {"type": "string"},
        "scrollTitle": {"type": "string"},
        "scrollBodyMarkdown": {"type": "string"},
    },
    "required": ["reading", "scrollTitle", "scrollBodyMarkdown"],
    "additionalProperties": False,
}


def persona() -> str:
    return resources.files("heavymetal.wizzy").joinpath("prompts/writer.md").read_text()


def system_blocks() -> list[dict]:
    # One stable block, cached: persona + style guide + examples. Facts go in the user turn after it.
    return [{"type": "text", "text": persona(), "cache_control": {"type": "ephemeral"}}]


@dataclass
class Written:
    reading: str
    title: str
    body: str
    templated: bool
    attempts: int = 0
    cost_usd: float = 0.0
    model: str | None = None
    problems: list[str] = field(default_factory=list)


def with_footer(text: str) -> str:
    text = text.rstrip()
    return text if FOOTER in text else f"{text}\n\n{FOOTER}"


# ---------------------------------------------------------------------- number formatting for templates
def usd(v: float | None) -> str:
    if v is None:
        return "?"
    a = abs(v)
    if a >= 1e9:
        return f"${v / 1e9:.2f}B"
    if a >= 1e6:
        return f"${v / 1e6:.2f}M"
    if a >= 1e3:
        return f"${v / 1e3:.1f}K"
    if a >= 1:
        return f"${v:,.2f}"
    return f"${v:.8f}".rstrip("0").rstrip(".") if v else "$0"


def pct(v: float | None) -> str:
    return "?" if v is None else f"{v:+.1f}%" if v < 0 or v > 0 else "0%"


def num(v: float | None) -> str:
    if v is None:
        return "?"
    if abs(v) >= 100:
        return f"{v:,.0f}"
    if abs(v) >= 1 or v == 0:
        return f"{v:,.2f}"
    return f"{v:.6f}".rstrip("0")


# ---------------------------------------------------------------------- templates (no LLM)
def template(facts: Facts) -> tuple[str, str, str]:
    if facts.wallet is not None:
        return _template_wallet(facts)
    return _template_token(facts)


def _template_token(f: Facts) -> tuple[str, str, str]:
    t = f.token
    sym = f"${t.symbol}" if t.symbol else "this token"
    kind = t.omen.kind if t.omen else "murky"
    glyph = OMEN_GLYPH[kind]
    auth = []
    auth.append("mint authority revoked" if t.authorities.mint is None else "mint authority still active")
    auth.append("freeze authority revoked" if t.authorities.freeze is None else "freeze authority still active")
    covered = ("authority",)  # stated in the authorities sentence below
    candidates = f.riskFlags + [r for r in f.strengths if not any(c in r.lower() for c in covered)]
    lead = candidates[0] if candidates else ""
    parts = [f"{glyph} {sym}: {OMEN_LINE[kind]}"]
    if lead:
        parts.append(lead.rstrip(".") + ".")
    if t.liquidityUsd is not None:
        parts.append(f"Liquidity {usd(t.liquidityUsd)}, FDV {usd(t.fdvUsd)}, 24h {pct(t.priceChange24hPct)}.")
    parts.append(", ".join(auth).capitalize() + ".")
    reading = " ".join(parts)
    title = f"{sym}: {kind}"
    lines = [
        "## Overview",
        f"- Omen: {kind}",
        f"- Price: {usd(t.priceUsd)}",
        f"- 24h move: {pct(t.priceChange24hPct)}",
        "## Tokenomics",
        f"- Liquidity: {usd(t.liquidityUsd)}",
        f"- FDV: {usd(t.fdvUsd)}",
        f"- Market cap: {usd(t.mcapUsd)}",
        f"- Total supply: {num(t.supply.total)}",
        "## On-chain",
        f"- Mint authority: {'revoked' if t.authorities.mint is None else 'active'}",
        f"- Freeze authority: {'revoked' if t.authorities.freeze is None else 'active'}",
        f"- Top 10 holders: {'?' if t.holders.top10Pct is None else str(t.holders.top10Pct) + '%'}",
        f"- Holders: {num(t.holders.countApprox) if t.holders.countApprox is not None else '?'}",
        f"- LP locked: {'?' if t.lpLockedPct is None else str(t.lpLockedPct) + '%'}",
        "## Risks",
        *([f"- {r}" for r in f.riskFlags] or ["- The bones found none in the code checks."]),
        "## Unknowns",
        *([f"- The mist hides: {u}" for u in f.unknowns] or ["- Nothing hidden."]),
    ]
    return reading, title, "\n".join(lines)


def _template_wallet(f: Facts) -> tuple[str, str, str]:
    w = f.wallet
    top = w.topHoldings[:3]
    held = ", ".join(f"${h.symbol or h.mint[:4]} {h.sharePct}%" for h in top if h.sharePct is not None)
    reading = f"🌫 A wallet of {usd(w.totalUsd)} across {w.tokenCount} tokens and {num(w.solBalance)} SOL."
    if held:
        reading += f" Its largest familiars: {held}."
    lines = [
        "## Overview",
        f"- Value: {usd(w.totalUsd)}",
        f"- SOL: {num(w.solBalance)}",
        f"- Tokens: {w.tokenCount}",
        "## Holdings",
        *[
            f"- {h.symbol or h.mint}: {usd(h.usd)} ({h.sharePct if h.sharePct is not None else '?'}%)"
            for h in w.topHoldings
        ],
        "## Concentration",
        f"- Largest holding: {top[0].sharePct}%" if top and top[0].sharePct is not None else "- Unknown",
        "## Risks",
        *([f"- {r}" for r in f.riskFlags] or ["- The bones found none."]),
        "## Unknowns",
        *([f"- The mist hides: {u}" for u in f.unknowns] or ["- Nothing hidden."]),
    ]
    return reading, "A wallet reading", "\n".join(lines)


# ---------------------------------------------------------------------- the writer
def user_prompt(facts: Facts, instructions: str = "", problems: list[str] | None = None) -> str:
    kind = facts.subject.kind
    glyph = OMEN_GLYPH[facts.token.omen.kind] if facts.token and facts.token.omen else "🌫"
    msg = [
        f"Subject kind: {kind}. Omen glyph: {glyph}.",
        instructions,
        "FACTS:",
        "```json",
        json.dumps(facts.for_writer(), default=str, separators=(",", ":")),
        "```",
    ]
    if problems:
        msg.append(
            "Your previous draft used values that are NOT in FACTS: "
            + "; ".join(problems[:12])
            + ". Rewrite it using only values present in FACTS."
        )
    return "\n".join(m for m in msg if m)


async def write(
    llm,
    facts: Facts,
    *,
    effort: str = "medium",
    instructions: str = "",
    extra_urls: list[str] | None = None,
    template_fn=None,
) -> Written:
    """Write a reading for facts. llm=None (no key, over budget) uses the code template."""
    allowed = guard.allowed_from(facts.for_writer(), extra_urls)
    template_fn = template_fn or template
    if llm is None:
        r, t, b = template_fn(facts)
        return Written(with_footer(r), t, with_footer(b), templated=True)
    cost, problems, model = 0.0, [], None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            data, resp = await llm.parse_structured(
                system_blocks(), user_prompt(facts, instructions, problems), SCHEMA, effort=effort, max_tokens=4000
            )
        except Exception as e:  # noqa: BLE001 - refusal, API error, bad JSON: fall back to the template
            problems = [f"writer error: {type(e).__name__}"]
            break
        cost += resp.cost_usd or 0.0
        model = resp.model
        texts = [data.get("reading", ""), data.get("scrollTitle", ""), data.get("scrollBodyMarkdown", "")]
        problems = [p for txt in texts for p in guard.check(txt, allowed)]
        if not problems and all(texts):
            return Written(
                with_footer(texts[0]),
                texts[1][:80],
                with_footer(texts[2]),
                templated=False,
                attempts=attempt,
                cost_usd=cost,
                model=model,
            )
    r, t, b = template(facts)
    return Written(
        with_footer(r),
        t,
        with_footer(b),
        templated=True,
        attempts=MAX_RETRIES + 1,
        cost_usd=cost,
        model=model,
        problems=problems,
    )
