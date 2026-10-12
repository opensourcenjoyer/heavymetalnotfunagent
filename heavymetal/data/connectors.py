"""Connector registry: which data sources exist, which keys they need, and what each one unlocks.

Keys are entered by the user with `/keys set <name>` (hidden input), never through the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Connector:
    name: str
    key_field: str | None  # attribute on cfg.keys, None = keyless
    env_var: str | None
    unlocks: str
    signup: str = ""
    secret: bool = True


CONNECTORS: list[Connector] = [
    Connector("geckoterminal", None, None, "pools, new pools, OHLCV, buyers/sellers (scanner, trenches, farm filter)"),
    Connector("defillama", None, None, "chain DEX volume history (trenches backfill)"),
    Connector("dexscreener", None, None, "pairs, prices, batch quotes (signal marks)"),
    Connector(
        "dune",
        "dune",
        "DUNE_API_KEY",
        "full-population smallcap volume (every trade, not a top-200 sweep)",
        "https://dune.com/settings/api",
    ),
    Connector(
        "dune_query_id",
        "dune_query_id",
        "HM_DUNE_QUERY_ID",
        "id of your saved Trenches query (paste the SQL from /trenches sql)",
        "https://dune.com/queries",
        secret=False,
    ),
    Connector(
        "birdeye",
        "birdeye",
        "BIRDEYE_API_KEY",
        "unique wallets per token: sharper inorganic/farm detection",
        "https://bds.birdeye.so",
    ),
    Connector(
        "helius",
        "helius",
        "HELIUS_API_KEY",
        "parsed swaps per wallet: fee-farm and round-trip detection",
        "https://dashboard.helius.dev",
    ),
]
BY_NAME = {c.name: c for c in CONNECTORS}
KEYED = [c.name for c in CONNECTORS if c.key_field]


def mask(v: str) -> str:
    if not v:
        return ""
    return v if len(v) <= 8 else v[:4] + "…" + v[-4:]


def status(cfg) -> list[dict]:
    out = []
    for c in CONNECTORS:
        val = getattr(cfg.keys, c.key_field) if c.key_field else None
        out.append(
            {
                "name": c.name,
                "keyless": c.key_field is None,
                "configured": c.key_field is None or bool(val),
                "value": (mask(val) if c.secret else val) if val else "",
                "unlocks": c.unlocks,
                "signup": c.signup,
                "env_var": c.env_var,
            }
        )
    return out


def missing(cfg) -> list[str]:
    return [s["name"] for s in status(cfg) if not s["configured"]]
