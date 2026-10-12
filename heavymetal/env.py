"""AgentEnv: everything a tool needs, built once at startup."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx
from solders.keypair import Keypair

from heavymetal.config import Config
from heavymetal.data.birdeye import Birdeye
from heavymetal.data.defillama import DefiLlama
from heavymetal.data.dune import Dune
from heavymetal.data.geckoterminal import GeckoTerminal
from heavymetal.data.helius import Helius
from heavymetal.decide import make_decider
from heavymetal.memory import DB
from heavymetal.providers import AnthropicProvider, OpenAICompatProvider
from heavymetal.solana.dexscreener import Dexscreener
from heavymetal.solana.jupiter import Jupiter
from heavymetal.solana.pumpportal import PumpPortal
from heavymetal.solana.rpc import RPC
from heavymetal.solana.rugcheck import RugCheck


@dataclass
class AgentEnv:
    cfg: Config
    kp: Keypair
    http: httpx.AsyncClient
    rpc: RPC
    db: DB
    session_id: str
    agent_llm: Any  # OpenAICompatProvider | AnthropicProvider
    decider: object  # DecisionsDecider | ChatDecider
    dex: Dexscreener
    rug: RugCheck
    jup: Jupiter
    pump: PumpPortal
    gecko: GeckoTerminal | None = None
    llama: DefiLlama | None = None
    dune: Dune | None = None
    birdeye: Birdeye | None = None
    helius: Helius | None = None
    scanner: Any = None  # heavymetal.signals.scanner.Scanner while running
    messages: list[dict] = field(default_factory=list)  # live conversation (for the reviewer)
    research: dict[str, set[str]] = field(default_factory=dict)  # mint -> research tools run this session
    on_event: object = None  # callable(kind, payload) for the UI

    @property
    def address(self) -> str:
        return str(self.kp.pubkey())

    @property
    def cluster(self) -> str:
        return self.cfg.solana.cluster

    def emit(self, kind: str, payload: dict) -> None:
        if callable(self.on_event):
            self.on_event(kind, payload)


def make_agent_llm(cfg: Config, model: str):
    if model.startswith("claude-"):
        is_anthropic = True
    elif "/" in model:
        is_anthropic = False
    elif cfg.llm.provider == "anthropic":
        is_anthropic = True
    elif cfg.llm.provider in ("openrouter", "openai"):
        is_anthropic = False
    else:
        is_anthropic = bool(cfg.llm.anthropic_key) and not bool(cfg.llm.api_key)

    if is_anthropic:
        return AnthropicProvider(api_key=cfg.llm.anthropic_key or cfg.llm.api_key, model=model)
    return OpenAICompatProvider(cfg.llm.api_key, model, cfg.llm.base_url, cfg.llm.zdr)


def build_env(cfg: Config, kp: Keypair, db: DB, session_id: str) -> AgentEnv:
    http = httpx.AsyncClient(headers={"User-Agent": "heavymetalagent/0.0.1"}, follow_redirects=True)
    env = AgentEnv(
        cfg=cfg,
        kp=kp,
        http=http,
        rpc=RPC(cfg.rpc_urls(), http),
        db=db,
        session_id=session_id,
        agent_llm=make_agent_llm(cfg, cfg.llm.agent_model),
        decider=make_decider(cfg, http),
        dex=Dexscreener(http),
        rug=RugCheck(http),
        jup=Jupiter(http, cfg.keys.jupiter),
        pump=PumpPortal(http),
        gecko=GeckoTerminal(http),
        llama=DefiLlama(http),
        dune=Dune(http, lambda: cfg.keys.dune),
        birdeye=Birdeye(http, lambda: cfg.keys.birdeye),
        helius=Helius(http, lambda: cfg.keys.helius),
    )
    env.rpc.on_failover = lambda old, new, why: env.emit(
        "rpc_failover", {"from": cfg.node_name(old) or "node", "to": cfg.node_name(new) or "node", "reason": why}
    )
    return env
