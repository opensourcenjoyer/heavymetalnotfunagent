"""Rug scrying: a quick risk omen from the code-only audit verdict.

cursed  = fake token, active freeze authority (honeypot risk) or critical RugCheck score
hexed   = farmed / wash-traded volume
murky   = nothing fatal, but not enough positives
blessed = revoked authorities, real liquidity, healthy distribution, no warnings
"""

from __future__ import annotations

from heavymetal.solana.fake_check import CANONICAL_MINTS
from heavymetal.trenches.gates import MAJOR_MINTS
from heavymetal.wizzy.facts import Omen

VERDICT_OMEN = {
    "FAKE": "cursed",
    "HONEYPOT": "cursed",
    "HIGH_RISK": "cursed",
    "FARM": "hexed",
    "SPECULATIVE": "murky",
    "HIGH_CONVICTION": "blessed",
}
OMEN_GLYPH = {"cursed": "☠", "hexed": "🜏", "murky": "🌫", "blessed": "✨"}
OMEN_LINE = {
    "cursed": "The bones say cursed.",
    "hexed": "A hex lies on this volume.",
    "murky": "The waters are murky.",
    "blessed": "The runes glow blessed.",
}
ESTABLISHED = set(CANONICAL_MINTS.values()) | set(MAJOR_MINTS)


def omen_for(mint: str, verdict_key: str | None, reasons: list[str] | None = None) -> Omen:
    reasons = list(reasons or [])[:3]
    kind = VERDICT_OMEN.get(verdict_key or "", "murky")
    if mint in ESTABLISHED and kind in ("cursed", "hexed"):
        # Stablecoins and majors may keep a freeze authority by design, and majors attract farm bots;
        # neither makes the token itself cursed.
        kind = "murky"
        if verdict_key == "HONEYPOT":
            reasons = ["An established token: its issuer keeps admin authorities by design.", *reasons[1:3]]
    return Omen(kind=kind, reasons=reasons)
