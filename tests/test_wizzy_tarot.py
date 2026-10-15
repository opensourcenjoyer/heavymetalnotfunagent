import asyncio

from heavymetal.wizzy import tarot
from heavymetal.wizzy.facts import Holding, WalletFacts
from heavymetal.wizzy.guard import allowed_from, check
from heavymetal.wizzy.resolve import Subject
from tests.wizzy_fakes import WALLET, FakeRPC, make_ctx

A, B, C, D = "MintA", "MintB", "MintC", "MintD"


def run(c):
    return asyncio.run(c)


def trade(ts, kind, mint, d, sol):
    return {
        "signature": f"s{ts}{mint}",
        "time": ts,
        "kind": kind,
        "sol_delta": sol,
        "token_deltas": {mint: d},
        "failed": False,
    }


def flipper_history():
    out = []
    for i, m in enumerate([A, B, C, D]):
        t = 1_700_000_000 + i * 600
        out += [trade(t, "buy", m, 100, -0.05), trade(t + 300, "sell", m, -100, 0.06)]
    return out


def test_history_stats_flips_and_sold_out():
    s = tarot.history_stats(flipper_history(), held_mints=set())
    assert s["buys"] == 4 and s["sells"] == 4 and s["flipsUnder1h"] == 4
    assert s["soldOutMints"] == 4 and s["mintsTraded"] == 4 and s["avgSolPerBuy"] == 0.05


def test_past_cards_trigger():
    names = {c.name for c in tarot.past_cards(tarot.history_stats(flipper_history(), set()))}
    assert {"Death", "Wheel of Fortune"} <= names
    assert tarot.past_cards(tarot.history_stats([], set())) == []


def test_present_and_future_cards():
    w = WalletFacts(
        address=WALLET,
        totalUsd=1000.0,
        solBalance=1.0,
        solUsdPrice=100.0,
        tokenCount=2,
        topHoldings=[
            Holding(mint=A, symbol="AAA", usd=800.0, sharePct=80.0),
            Holding(mint=B, symbol="BBB", usd=100.0, sharePct=10.0),
        ],
    )
    assert tarot.present_cards(w)[0].name == "The Hermit"
    fut = tarot.future_cards([{"symbol": "AAA", "omen": "cursed", "sharePct": 80.0, "change24hPct": 50.0}])
    assert {c.name for c in fut} == {"The Tower", "The Star"}
    assert max(fut, key=lambda c: c.score).name == "The Tower"


def test_pick_is_stable_for_a_day_and_falls_back_to_moon():
    a = tarot.Card("A", "a", "past", "", 0.5)
    b = tarot.Card("B", "b", "past", "", 0.5)
    s1 = tarot.seed(WALLET, "2026-10-16")
    assert tarot.seed(WALLET, "2026-10-16") == s1
    assert tarot.pick([a, b], "past", s1).name == tarot.pick([b, a], "past", s1).name
    assert tarot.pick([], "future", s1).name == "The Moon"


class HistRPC(FakeRPC):
    def __init__(self, n):
        super().__init__(mints=())
        self.n = n
        self.fetched = 0

    async def signatures(self, addr, limit):
        return [{"signature": f"sig{i}"} for i in range(min(limit, self.n))]

    async def transaction(self, sig):
        self.fetched += 1
        return None


def test_history_respects_signature_cap(tmp_path):
    ctx = make_ctx(tmp_path, rpc=HistRPC(500))
    trades, source = run(tarot.wallet_history(ctx.env, WALLET, max_sigs=40))
    assert source == "rpc" and ctx.env.rpc.fetched == 40 and trades == []


def test_tarot_facts_template_passes_guard_and_pipeline_saves_cards(tmp_path, monkeypatch):
    ctx = make_ctx(tmp_path, rpc=HistRPC(3))

    async def no_omens(env, w, limit=3):
        return [{"mint": A, "symbol": "MOSS", "sharePct": 100.0, "omen": "hexed", "change24hPct": 5.0}]

    monkeypatch.setattr(tarot, "holding_omens", no_omens)
    facts, cards = run(tarot.build_tarot_facts(ctx.env, Subject("wallet", WALLET), max_sigs=10))
    assert cards["future"].name == "The Tower" and cards["past"].name == "The Moon"
    r, _t, b = tarot.template(facts)
    a = allowed_from(facts.for_writer())
    assert check(r, a) == [] and check(b, a) == []
    scroll, _url, cached = run(tarot.tarot_read(ctx, WALLET, user_id=None, surface="cli"))
    assert scroll.kind == "tarot" and [c["slot"] for c in scroll.meta["cards"]] == ["past", "present", "future"]
    assert not cached and run(tarot.tarot_read(ctx, WALLET, user_id=None, surface="cli"))[2] is True


def test_tarot_refuses_tokens(tmp_path):
    from heavymetal.wizzy.bots.core import act
    from heavymetal.wizzy.router import Intent
    from tests.wizzy_fakes import NEW_MINT

    tarot.register()
    ctx = make_ctx(tmp_path)
    r = run(act(ctx, 1, Intent("tarot", NEW_MINT), surface="tg"))
    assert r.kind == "error" and "wallet" in r.text
