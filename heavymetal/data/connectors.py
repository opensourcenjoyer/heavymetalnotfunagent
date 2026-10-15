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
    group: str = "data"  # data: heavymetal sources | wizzy: the public bot's credentials


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

WIZZY_CONNECTORS: list[Connector] = [
    Connector(
        "telegram_bot_token",
        "telegram_bot_token",
        "TELEGRAM_BOT_TOKEN",
        "Wizzy Telegram bot",
        "https://t.me/BotFather",
        group="wizzy",
    ),
    Connector(
        "telegram_webhook_secret",
        "telegram_webhook_secret",
        "TELEGRAM_WEBHOOK_SECRET",
        "verifies Telegram webhook calls",
        group="wizzy",
    ),
    Connector(
        "x_bearer_token",
        "x_bearer_token",
        "X_BEARER_TOKEN",
        "Wizzy reads X mentions",
        "https://developer.x.com",
        group="wizzy",
    ),
    Connector(
        "x_api_key",
        "x_api_key",
        "X_API_KEY",
        "Wizzy posts on X (OAuth 1.0a consumer key)",
        "https://developer.x.com",
        group="wizzy",
    ),
    Connector("x_api_secret", "x_api_secret", "X_API_SECRET", "Wizzy posts on X (consumer secret)", group="wizzy"),
    Connector("x_access_token", "x_access_token", "X_ACCESS_TOKEN", "Wizzy posts on X (access token)", group="wizzy"),
    Connector(
        "x_access_secret", "x_access_secret", "X_ACCESS_SECRET", "Wizzy posts on X (access secret)", group="wizzy"
    ),
    Connector(
        "x_user_id", "x_user_id", "X_USER_ID", "Wizzy's X account id (mentions timeline)", secret=False, group="wizzy"
    ),
    Connector(
        "quickchart_api_key",
        "quickchart_api_key",
        "QUICKCHART_API_KEY",
        "higher QuickChart limits for scroll charts",
        "https://quickchart.io",
        group="wizzy",
    ),
    Connector("sentry_dsn", "sentry_dsn", "SENTRY_DSN", "Wizzy error reporting", "https://sentry.io", group="wizzy"),
]
BY_NAME = {c.name: c for c in CONNECTORS + WIZZY_CONNECTORS}
KEYED = [c.name for c in CONNECTORS + WIZZY_CONNECTORS if c.key_field]


def mask(v: str) -> str:
    if not v:
        return ""
    return v if len(v) <= 8 else v[:4] + "…" + v[-4:]


def status(cfg, group: str = "data") -> list[dict]:
    out = []
    for c in CONNECTORS + WIZZY_CONNECTORS:
        if c.group != group:
            continue
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


def missing(cfg, group: str = "data") -> list[str]:
    return [s["name"] for s in status(cfg, group) if not s["configured"]]
