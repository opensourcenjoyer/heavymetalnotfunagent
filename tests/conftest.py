import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from heavymetal.config import Config
from heavymetal.decide import DecideResult, Decision
from heavymetal.memory import DB

MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"


class FakeDecider:
    """Answers review questions from a dict {key: bool | Exception}. Defaults = a clean, user-requested trade."""

    kind = "fake"
    model = "fake/jev"
    DEFAULTS = {
        "user_requested": True,
        "params_ok": True,
        "manipulation": False,
        "intended_repeat": True,
        "fake_or_copycat": False,
    }

    def __init__(self, answers: dict):
        self.answers = answers
        self.calls = []

    async def decide(self, questions, state):
        self.calls.extend(q.key for q in questions)
        self.state = state
        ans, errs = {}, {}
        for q in questions:
            a = self.answers.get(q.key, self.DEFAULTS[q.key])
            if isinstance(a, Exception):
                errs[q.key] = str(a)
            else:
                ans[q.key] = Decision(a, 0.9 if a else 0.1, "fake")
        return DecideResult(ans, errs, self.model, 0.0001, 10, 5, 0.01)


class FakeRPC:
    def __init__(self, balance_sol=1.0, freeze=None):
        self.balance = int(balance_sol * 1e9)
        self.freeze = freeze

    async def balance_lamports(self, address):
        return self.balance

    async def mint_info(self, mint):
        return {
            "decimals": 6,
            "supply": 10**15,
            "program": "Tokenkeg",
            "mint_authority": None,
            "freeze_authority": self.freeze,
        }


class FakeDex:
    def __init__(self, liquidity_usd=500_000):
        self.liq = liquidity_usd

    async def token_pairs(self, mint):
        return [
            {
                "base": {"symbol": "BONK", "name": "Bonk", "address": mint},
                "liquidity_usd": self.liq,
                "sol_usd": 150.0,
                "age_hours": 5000,
            }
        ]


@pytest.fixture
def make_env(tmp_path):
    def _make(answers=None, balance_sol=1.0, freeze=None, liquidity_usd=500_000, research=True, messages=None):
        cfg = Config()
        db = DB(tmp_path / "t.db")
        env = SimpleNamespace(
            cfg=cfg,
            db=db,
            session_id="s1",
            address="Agent1111111111111111111111111111111111111",
            rpc=FakeRPC(balance_sol, freeze),
            dex=FakeDex(liquidity_usd),
            decider=FakeDecider(answers or {}),
            research={MINT: {"rug_check"}} if research else {},
            messages=messages if messages is not None else [{"role": "user", "content": f"buy 0.1 SOL of {MINT}"}],
            cluster="mainnet",
            events=[],
        )
        env.emit = lambda k, p: env.events.append((k, p))
        return env

    return _make


def run(coro):
    return asyncio.run(coro)


def add_confirmed_trade(env, minutes_ago=1):
    env.db.add_trade(env.session_id, "swap", "buy", MINT, 0.1, "SOL", None, {"status": "confirmed", "signature": "sig"})
    env.db.conn.execute("UPDATE trades SET ts=?", (time.time() - minutes_ago * 60,))
    env.db.conn.commit()


__all__ = ["MINT", "add_confirmed_trade", "json", "run"]
