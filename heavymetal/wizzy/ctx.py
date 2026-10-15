"""WizzyCtx: the read-only env (heavymetal data clients + heavymetal DB) plus Wizzy's own DB and settings."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from heavymetal import config as config_mod
from heavymetal.config import Config, WizzyConfig
from heavymetal.env import AgentEnv, build_reader_env
from heavymetal.memory import DB
from heavymetal.wizzy.db import WizzyDB


@dataclass
class WizzyCtx:
    env: AgentEnv
    wdb: WizzyDB
    writer: Any = None  # AnthropicProvider for readings (None: templated readings only)
    router_llm: Any = None  # cheap model for free-text intent (None: rules only)
    readings_sem: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(4))

    @property
    def cfg(self) -> Config:
        return self.env.cfg

    @property
    def wcfg(self) -> WizzyConfig:
        return self.env.cfg.wizzy

    async def aclose(self) -> None:
        await self.env.http.aclose()


def make_llms(cfg: Config) -> tuple[Any, Any]:
    """Writer and router providers, or (None, None) without an Anthropic key."""
    key = cfg.llm.anthropic_key
    if not key:
        return None, None
    from heavymetal.providers import AnthropicProvider

    return (
        AnthropicProvider(api_key=key, model=cfg.wizzy.writer_model),
        AnthropicProvider(api_key=key, model=cfg.wizzy.router_model),
    )


def open_ctx(cfg: Config | None = None, wdb_path: Path | str | None = None, db: DB | None = None) -> WizzyCtx:
    cfg = cfg or config_mod.load()
    db = db or DB()
    db.conn.execute("PRAGMA busy_timeout=5000")  # share heavymetal.db politely with a running REPL
    env = build_reader_env(cfg, db)
    writer, router = make_llms(env.cfg)
    ctx = WizzyCtx(env=env, wdb=WizzyDB(wdb_path), writer=writer, router_llm=router)
    ctx.readings_sem = asyncio.Semaphore(max(1, cfg.wizzy.max_concurrent_readings))
    return ctx
