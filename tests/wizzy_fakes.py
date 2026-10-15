"""Shared fakes for Wizzy tests: a reader env with scripted data sources and a scripted writer model."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from heavymetal.config import Config
from heavymetal.memory import DB
from heavymetal.providers.types import ProviderResponse
from heavymetal.wizzy.ctx import WizzyCtx
from heavymetal.wizzy.db import WizzyDB

MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"  # BONK (canonical)
NEW_MINT = "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"
WALLET = "Hx4MLyVMwb3VPYA9EDfT1CbMCiNqtHgMyQXnVM39Hw6x"


def pair(mint=NEW_MINT, symbol="MOSS", liq=48210.5, fdv=912000.0, name="Moss Coin"):
    return {
        "pair": "PAIR" + mint[:8],
        "dex": "raydium",
        "base": {"address": mint, "symbol": symbol, "name": name},
        "price_usd": 0.000912,
        "liquidity_usd": liq,
        "fdv": fdv,
        "market_cap": fdv,
        "volume": {"h24": 100000.0},
        "price_change": {"h24": -18.4},
    }


class FakeDex:
    def __init__(self, pairs=None, search=None):
        self.pairs = pairs if pairs is not None else [pair()]
        self.search_rows = search or []

    async def token_pairs(self, mint):
        return [p for p in self.pairs if p["base"]["address"] == mint]

    async def pair(self, addr):
        return None

    async def search(self, q, limit=10):
        return self.search_rows[:limit]

    async def tokens_batch(self, mints):
        return {p["base"]["address"]: p for p in self.pairs if p["base"]["address"] in mints}


class FakeRPC:
    def __init__(self, mints=(NEW_MINT, MINT), freeze=None):
        self.mints = set(mints)
        self.freeze = freeze

    async def mint_info(self, mint):
        if mint not in self.mints:
            raise ValueError("not a mint")
        return {
            "decimals": 6,
            "supply": 1_000_000_000 * 10**6,
            "program": "spl",
            "mint_authority": None,
            "freeze_authority": self.freeze,
        }

    async def largest_holders(self, mint):
        return [{"account": f"acct{i}", "amount": 41_200_000 * 10**6 / 10, "ui_amount": 1} for i in range(10)]

    async def balance_sol(self, addr):
        return 12.5

    async def token_accounts(self, addr):
        return [{"mint": NEW_MINT, "account": "a", "amount": 1, "decimals": 6, "ui_amount": 1000.0, "program": "spl"}]


class FakeRug:
    def __init__(self, fail_report=False):
        self.fail_report = fail_report

    async def summary(self, mint):
        return {"score_normalised": 10, "lp_locked_pct": 99.1, "risks": []}

    async def report(self, mint):
        if self.fail_report:
            raise RuntimeError("rugcheck down")
        return {"total_holders": 40211, "top10_pct": 41.2}


class FakeJup:
    async def prices(self, mints):
        return {m: 0.000912 for m in mints} | {"So11111111111111111111111111111111111111112": 150.0}


class FakeGecko:
    async def token_pools(self, mint):
        return [{"pool": "POOL1"}]

    async def ohlcv(self, pool, timeframe="hour", aggregate=1, limit=24):
        return [
            {
                "ts": i,
                "open": 1.0 + i / 100,
                "high": 1.1 + i / 100,
                "low": 0.9,
                "close": 1.0 + i / 100,
                "volume": 1000.0,
            }
            for i in range(24)
        ]


def reader_env(tmp_path, **kw):
    cfg = Config()
    return SimpleNamespace(
        cfg=cfg,
        db=DB(tmp_path / "hm.db"),
        dex=kw.get("dex") or FakeDex(),
        rpc=kw.get("rpc") or FakeRPC(),
        rug=kw.get("rug") or FakeRug(),
        jup=FakeJup(),
        gecko=FakeGecko(),
        birdeye=None,
        helius=None,
        llama=None,
        cluster="mainnet",
        kp=None,
    )


def make_ctx(tmp_path, writer=None, **kw):
    env = reader_env(tmp_path, **kw)
    return WizzyCtx(env=env, wdb=WizzyDB(tmp_path / "wizzy.db"), writer=writer, readings_sem=asyncio.Semaphore(2))


class ScriptedWriter:
    """Returns the scripted outputs in order (dict or Exception)."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    async def parse_structured(self, system_blocks, user, schema, **kw):
        self.calls.append(user)
        out = self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]
        if isinstance(out, Exception):
            raise out
        return out, ProviderResponse(
            content="", tool_calls=[], input_tokens=100, output_tokens=50, cost_usd=0.01, model="claude-opus-5-5"
        )
