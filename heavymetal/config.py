"""Config: ~/.heavymetal/config.toml (chmod 600). Env vars override file values."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit

import tomli_w

from heavymetal import paths

MAINNET_PUBLIC_RPC = "https://api.mainnet-beta.solana.com"
DEVNET_RPC = "https://api.devnet.solana.com"
ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-5-5"


@dataclass
class LLMConfig:
    provider: str = "auto"  # auto | anthropic | openrouter | openai
    base_url: str = "https://openrouter.ai/api/v1"
    api_key: str = ""
    anthropic_key: str = ""  # Anthropic API key (sk-ant-...)
    zdr: bool = True  # OpenRouter: only route to Zero Data Retention endpoints
    agent_model: str = "deepseek/deepseek-v4-flash"
    review_model: str = "typesafe/jev-1.13"
    review_api: str = "auto"  # auto | decisions | chat  (auto: decisions for typesafe/jev-1.x)
    max_iterations: int = 25


@dataclass
class ReviewConfig:
    mode: str = "gate"  # gate | advise | off
    actions: list[str] = field(default_factory=lambda: ["swap", "pump_trade", "buy_with_tpsl", "close_position"])
    on_error: str = "block"  # block | allow  (when the review model fails)
    require_research: bool = True  # buys need rug_check/token_info on the mint first
    max_liquidity_pct: float = 2.0  # buy size cap as % of pool liquidity -> REDUCE_SIZE
    duplicate_window_min: int = 10
    threshold: float = 0.5  # decisions models: p(true) >= threshold counts as true


def default_nodes() -> dict[str, dict]:
    return {
        "public": {"url": MAINNET_PUBLIC_RPC, "cluster": "mainnet"},
        "devnet": {"url": DEVNET_RPC, "cluster": "devnet"},
    }


@dataclass
class SolanaConfig:
    rpc_url: str = MAINNET_PUBLIC_RPC  # the active node
    cluster: str = "mainnet"  # follows the active node: mainnet | devnet | testnet | localnet
    rpc_fallback: bool = True  # fail over to other saved nodes on the same cluster
    rpc_nodes: dict[str, dict] = field(default_factory=default_nodes)  # name -> {url, cluster}


@dataclass
class TradeConfig:
    slippage_pct: float = 10.0
    priority_fee_sol: float = 0.0001


@dataclass
class KeysConfig:
    jupiter: str = ""
    pinata_jwt: str = ""
    dune: str = ""  # Dune Analytics API key: full-population smallcap volume for Trenches
    dune_query_id: str = ""  # your saved copy of the Trenches SQL (/trenches sql)
    birdeye: str = ""  # Birdeye API key: unique wallets per token (farm filter)
    helius: str = ""  # Helius API key: parsed swaps per wallet (fee-farm detection)


@dataclass
class SignalsConfig:
    scanner: bool = True  # background scanner while the REPL is open (mainnet only)
    scan_interval_s: int = 60  # GeckoTerminal new_pools poll
    mark_interval_s: int = 300  # refresh price/FDV of tracked signals
    pulse_interval_s: int = 900  # refresh the Trenches sweep + bank the day
    min_volume_h24: float = 25_000  # a launch must trade this much in 24h to become a signal
    min_liquidity_usd: float = 5_000  # ... and hold at least this much liquidity
    milestone_min_liq: float = 25_000  # milestones (2x..100x) only count at this liquidity or more
    track_days: int = 14  # signals stop being marked after this many days
    alerts: list[str] = field(default_factory=lambda: ["HIGH_CONVICTION", "SPECULATIVE"])  # verdicts to alert on
    # farm gates (Fair-style): see heavymetal/signals/farm.py
    wash_turnover: float = 300.0  # 24h volume / liquidity above this = bot churning an empty book
    loop_turnover: float = 100.0  # flat-price loops: turnover above this with a flat price and 50/50 flow
    feefarm_swaps_per_wallet: float = 15.0  # swaps a wallet a day through a near-zero-fee pool
    roundtrip_swaps_per_wallet: float = 100.0  # swaps a wallet a day anywhere = round-tripping
    min_crowd_wallets: int = 25  # fewer wallets than this carrying min_crowd_volume = not a crowd
    min_crowd_volume: float = 50_000
    zero_reserve_usd_per_wallet: float = 10_000  # unreadable liquidity carrying more than this per wallet
    smallcap_fdv_cap: float = 200_000_000
    deny_mints: list[str] = field(default_factory=list)  # excluded by hand (known bot loops, relaunches)
    # fear & greed fixed normals (override after re-measuring; see heavymetal/trenches/fear_greed.py)
    fg_volume_normal: float = 0.0  # 0 = built-in default
    fg_hold_normal: float = 0.0
    fg_ceiling_normal: float = 0.0


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    solana: SolanaConfig = field(default_factory=SolanaConfig)
    trade: TradeConfig = field(default_factory=TradeConfig)
    keys: KeysConfig = field(default_factory=KeysConfig)
    signals: SignalsConfig = field(default_factory=SignalsConfig)

    def node_name(self, url: str | None = None) -> str | None:
        url = url or self.solana.rpc_url
        return next((n for n, v in self.solana.rpc_nodes.items() if v["url"] == url), None)

    def rpc_urls(self) -> list[str]:
        """Active node first, then failover nodes on the same cluster (saved order)."""
        s = self.solana
        urls = [s.rpc_url]
        if s.rpc_fallback:
            urls += [v["url"] for v in s.rpc_nodes.values() if v.get("cluster") == s.cluster and v["url"] not in urls]
        return urls


def name_from_url(url: str, taken: set[str] = frozenset()) -> str:
    host = urlsplit(url).hostname or "node"
    known = {
        "quiknode": "quicknode",
        "helius": "helius",
        "alchemy": "alchemy",
        "triton": "triton",
        "ankr": "ankr",
        "syndica": "syndica",
        "localhost": "local",
        "127.0.0.1": "local",
    }
    base = next((v for k, v in known.items() if k in host), re.sub(r"[^a-z0-9]+", "-", host.split(".")[0]))
    name, i = base or "node", 2
    while name in taken:
        name, i = f"{base}{i}", i + 1
    return name


def normalize(cfg: Config) -> Config:
    """Make sure the active URL is a saved node and the cluster follows it."""
    s = cfg.solana
    s.rpc_nodes = {
        n: {"url": str(v.get("url", "")), "cluster": str(v.get("cluster", "mainnet"))}
        for n, v in (s.rpc_nodes or {}).items()
        if isinstance(v, dict) and v.get("url")
    }
    name = cfg.node_name()
    if name is None:
        s.rpc_nodes[name_from_url(s.rpc_url, set(s.rpc_nodes))] = {"url": s.rpc_url, "cluster": s.cluster}
    else:
        s.cluster = s.rpc_nodes[name]["cluster"]
    return cfg


def _merge(dc, data: dict):
    for k, v in (data or {}).items():
        if hasattr(dc, k):
            setattr(dc, k, v)


def load() -> Config:
    cfg = Config()
    p = paths.config_path()
    if p.exists():
        data = tomllib.loads(p.read_text())
        for section in ("llm", "review", "solana", "trade", "keys", "signals"):
            _merge(getattr(cfg, section), data.get(section, {}))
    env = os.environ
    cfg.llm.api_key = env.get("OPENROUTER_API_KEY", cfg.llm.api_key)
    cfg.llm.anthropic_key = env.get("ANTHROPIC_API_KEY", cfg.llm.anthropic_key)
    cfg.solana.rpc_url = env.get("HM_RPC_URL", cfg.solana.rpc_url)
    cfg.keys.jupiter = env.get("JUPITER_API_KEY", cfg.keys.jupiter)
    cfg.keys.pinata_jwt = env.get("PINATA_JWT", cfg.keys.pinata_jwt)
    cfg.keys.dune = env.get("DUNE_API_KEY", cfg.keys.dune)
    cfg.keys.dune_query_id = env.get("HM_DUNE_QUERY_ID", cfg.keys.dune_query_id)
    cfg.keys.birdeye = env.get("BIRDEYE_API_KEY", cfg.keys.birdeye)
    cfg.keys.helius = env.get("HELIUS_API_KEY", cfg.keys.helius)
    # Anthropic-only setup: an OpenRouter model id can't be served, so default to Claude.
    if (
        cfg.llm.anthropic_key
        and not cfg.llm.api_key
        and cfg.llm.provider in ("auto", "anthropic")
        and not cfg.llm.agent_model.startswith("claude-")
    ):
        cfg.llm.agent_model = ANTHROPIC_DEFAULT_MODEL
    return normalize(cfg)


def save(cfg: Config) -> None:
    p = paths.config_path()
    p.write_text(tomli_w.dumps(asdict(cfg)))
    p.chmod(0o600)


def wizard(cfg: Config) -> Config:
    """First-run prompts. Keys are stored only in ~/.heavymetal/config.toml (chmod 600)."""
    print("heavymetalagent first-run setup (stored in ~/.heavymetal/config.toml, chmod 600)\n")
    if not (cfg.llm.api_key or cfg.llm.anthropic_key):
        key = input("LLM API key (Anthropic sk-ant-... or OpenRouter sk-or-...): ").strip()
        if key.startswith("sk-ant-"):
            cfg.llm.anthropic_key = key
            cfg.llm.provider = "anthropic"
            cfg.llm.agent_model = ANTHROPIC_DEFAULT_MODEL
        else:
            cfg.llm.api_key = key
    rpc = input(f"Solana mainnet RPC URL, e.g. QuickNode [{cfg.solana.rpc_url}]: ").strip()
    if rpc:
        cfg.solana.rpc_nodes[name_from_url(rpc, set(cfg.solana.rpc_nodes))] = {"url": rpc, "cluster": "mainnet"}
        cfg.solana.rpc_url = rpc
    normalize(cfg)
    save(cfg)
    return cfg
