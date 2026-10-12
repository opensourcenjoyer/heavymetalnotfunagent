"""Buys sized in dollars ("buy $5 of X") and related trade-tool regressions."""

import json

import pytest
from conftest import MINT, run

from heavymetal.solana.constants import SOL_MINT
from heavymetal.tools import REGISTRY, execute
from heavymetal.tools import trade as trade_mod


class FakeJup:
    def __init__(self, price=100.0):
        self.price = price

    async def prices(self, mints):
        return {SOL_MINT: self.price}


@pytest.fixture
def usd_env(make_env):
    def _make(price=100.0, **kw):
        env = make_env(messages=[{"role": "user", "content": f"buy $5 of {MINT}"}], **kw)
        env.jup = FakeJup(price)
        return env

    return _make


def capture(monkeypatch, name, result=None):
    calls = []

    async def fake(env, **kw):
        calls.append(kw)
        return result or {"status": "confirmed", "signature": "sig"}

    monkeypatch.setattr(REGISTRY[name], "fn", fake)
    return calls


def test_usd_to_sol_conversion(usd_env):
    env = usd_env(price=125.0)
    args, meta = run(trade_mod.usd_to_sol(env, "swap", {"input_mint": "SOL", "output_mint": MINT, "amount_usd": 5}))
    assert args == {"input_mint": "SOL", "output_mint": MINT, "amount": 0.04}
    assert meta == {"requested_usd": 5.0, "sol_usd": 125.0}
    args, _ = run(trade_mod.usd_to_sol(env, "buy_with_tpsl", {"mint": MINT, "amount_usd": 10}))
    assert args["sol_amount"] == 0.08 and "amount_usd" not in args
    args, _ = run(trade_mod.usd_to_sol(env, "pump_trade", {"action": "buy", "mint": MINT, "amount_usd": 5}))
    assert args["amount"] == 0.04 and args["denominated_in_sol"] is True


def test_usd_rejected_for_sells(usd_env):
    env = usd_env()
    with pytest.raises(ValueError):
        run(trade_mod.usd_to_sol(env, "swap", {"input_mint": MINT, "output_mint": "SOL", "amount_usd": 5}))
    with pytest.raises(ValueError):
        run(trade_mod.usd_to_sol(env, "pump_trade", {"action": "sell", "mint": MINT, "amount_usd": 5}))


def test_usd_buy_is_converted_before_review_and_signing(usd_env, monkeypatch):
    env = usd_env(price=100.0)
    calls = capture(monkeypatch, "swap")
    out = json.loads(run(execute(env, "swap", {"input_mint": "SOL", "output_mint": MINT, "amount_usd": 5})))
    assert out["status"] == "confirmed", out
    assert calls == [{"input_mint": "SOL", "output_mint": MINT, "amount": 0.05}]  # tool got SOL, not USD
    assert out["usd_conversion"] == {"requested_usd": 5.0, "sol_usd": 100.0}
    st = env.decider.state["proposed_trade"]
    assert st["amount"] == 0.05 and st["unit"] == "SOL"
    assert st["requested_usd"] == 5.0 and st["amount_usd"] == 5.0  # same price used for conversion


def test_usd_buy_still_checks_balance(usd_env, monkeypatch):
    env = usd_env(price=100.0, balance_sol=0.02)
    calls = capture(monkeypatch, "swap")
    out = json.loads(run(execute(env, "swap", {"input_mint": "SOL", "output_mint": MINT, "amount_usd": 5})))
    assert out["status"] == "blocked" and out["verdict"] == "CORRECT_PARAMS"
    assert calls == []


def test_buy_with_tpsl_records_position_on_confirmed_swap(usd_env, monkeypatch):
    env = usd_env()
    tracked = []

    async def fake_swap(env, i, o, amt, slip=None):
        return {"status": "confirmed", "signature": "sig"}

    async def fake_track(**kw):
        tracked.append(kw)
        return {"id": 1}

    async def fake_resolve(env, target):
        raise RuntimeError("offline")

    import heavymetal.solana.positions as pos
    import heavymetal.solana.resolver as res

    monkeypatch.setattr(trade_mod, "swap", fake_swap)
    monkeypatch.setattr(pos, "track_new_position", fake_track)
    monkeypatch.setattr(res, "resolve_target", fake_resolve)
    out = run(trade_mod.buy_with_tpsl(env, MINT, sol_amount=0.05))
    assert out["status"] == "success" and len(tracked) == 1, out


def test_reduce_size_uses_sol_amount_for_buy_with_tpsl(make_env, monkeypatch):
    env = make_env(liquidity_usd=100)  # tiny pool -> REDUCE_SIZE
    env.messages[:] = [{"role": "user", "content": f"buy 0.1 SOL of {MINT} with tp/sl"}]
    calls = capture(monkeypatch, "buy_with_tpsl", {"status": "success"})
    out = json.loads(run(execute(env, "buy_with_tpsl", {"mint": MINT, "sol_amount": 0.1})))
    assert out["status"] == "success", out
    assert "amount" not in calls[0] and calls[0]["sol_amount"] < 0.1


def test_token_audit_counts_as_research_for_resolved_mint(make_env, monkeypatch):
    env = make_env(research=False)
    capture(monkeypatch, "token_audit", {"status": "success", "mint": MINT})
    run(execute(env, "token_audit", {"target": f"https://dexscreener.com/solana/{MINT}"}))
    assert "token_audit" in env.research.get(MINT, set())


def test_sell_all_reports_pct_of_holdings(make_env):
    from heavymetal.review import review_trade

    env = make_env(messages=[{"role": "user", "content": "sell all"}])

    async def token_accounts(owner):
        return [{"mint": MINT, "ui_amount": 226.18}]

    env.rpc.token_accounts = token_accounts
    run(review_trade(env, "swap", {"input_mint": MINT, "output_mint": "SOL", "amount": 226.18}))
    assert env.decider.state["proposed_trade"]["pct_of_holdings"] == 100.0


def test_stated_usd_cap_parsing():
    from heavymetal.review import stated_usd_cap

    assert stated_usd_cap("can you buy this token on 2$ pls") == 2
    assert stated_usd_cap("buy $5 of BONK") == 5
    assert stated_usd_cap("buy 10 usd of it, price is $0.03") == 10
    assert stated_usd_cap("buy 0.1 SOL if it's under $5") is None  # sized in SOL: no dollar cap
    assert stated_usd_cap("buy the best one") is None


def test_dollar_buy_far_above_request_is_blocked_in_code(make_env):
    from heavymetal.review import review_trade

    # FakeDex quotes SOL at $150: 0.1 SOL = $15 but the user asked for $2
    env = make_env(messages=[{"role": "user", "content": f"buy $2 of {MINT}"}])
    v = run(review_trade(env, "swap", {"input_mint": "SOL", "output_mint": MINT, "amount": 0.1}))
    assert v["verdict"] == "CORRECT_PARAMS" and "$2" in v["reasons"][0]
    v = run(review_trade(env, "swap", {"input_mint": "SOL", "output_mint": MINT, "amount": 0.0135}))  # ~$2.03
    assert v["verdict"] == "EXECUTE", v
