import asyncio
import json
import time

import pytest

from heavymetal.wizzy import familiars
from heavymetal.wizzy.spellbook import poll, surface
from heavymetal.wizzy.spellbook import watches as W
from tests.wizzy_fakes import NEW_MINT, WALLET, FakeDex, make_ctx, pair


def run(c):
    return asyncio.run(c)


@pytest.mark.parametrize(
    ("text", "kind", "target"),
    [
        ("warn me if JUP's top holders move", "holders_moved", "$JUP"),
        ("watch $WIF liquidity drops 30%", "liquidity_drop", "$WIF"),
        (f"tell me if {WALLET} moves over 50 SOL", "wallet_moves", WALLET),
        ("alert me if $MOSS freeze authority changes", "authority_change", "$MOSS"),
        ("tell me about unlocks before they hit for $JTO", "unlock", "$JTO"),
        ("ping me sometime", None, None),
    ],
)
def test_parse(text, kind, target):
    d = W.parse(text)
    assert d.kind == kind and d.target == target


def test_parse_thresholds():
    assert W.parse("watch $WIF liquidity drops 30%").params["drop_pct"] == 30.0
    assert W.parse(f"tell me if {WALLET} moves over 50 SOL").params["min_sol"] == 50.0


def test_holders_and_authority_and_wallet_diffs():
    old = W.holders_state([{"account": "a", "amount": 100}, {"account": "b", "amount": 50}], 1000)
    new = W.holders_state([{"account": "a", "amount": 60}, {"account": "c", "amount": 50}], 1000)
    whats = {e["what"] for e in W.holders_diff(old, new, {"pp": 2.0, "holder_pct": 10.0})}
    assert whats == {"top10_shift", "holder_moved", "left_top10"}
    assert W.authority_diff({}, {"mint_authority": None}) == []
    assert W.authority_diff({"freeze_authority": None}, {"freeze_authority": "X"})[0]["field"] == "freeze_authority"
    evs = W.wallet_events(
        [
            {"signature": "s1", "kind": "sol_out", "sol_delta": -60, "token_deltas": {}},
            {"signature": "s2", "kind": "sol_out", "sol_delta": -1, "token_deltas": {}},
        ],
        {"min_sol": 50},
    )
    assert [e["key"] for e in evs] == ["tx:s1"]


def test_liquidity_diff_rolls_baseline():
    ev, st = W.liquidity_diff({}, 100_000, {"drop_pct": 25})
    assert ev == [] and st["baseline"] == 100_000
    ev, st = W.liquidity_diff(st, 90_000, {"drop_pct": 25})
    assert ev == [] and st["baseline"] == 100_000
    ev, st = W.liquidity_diff(st, 70_000, {"drop_pct": 25})
    assert ev[0]["drop_pct"] == 30.0 and st["baseline"] == 70_000


def _watch(ctx, kind="liquidity_drop", target=NEW_MINT, params=None, uid=None, cooldown=3600):
    uid = uid or ctx.wdb.user(tg_id="100")["id"]
    wid = W.create(ctx.wdb, uid, kind, target, params or {"drop_pct": 25.0}, "100", active=True)
    ctx.wdb._x("UPDATE watches SET cooldown_s=? WHERE id=?", (cooldown, wid))
    return wid


def test_poll_liquidity_fires_once_with_dedupe_and_cooldown(tmp_path):
    dex = FakeDex(pairs=[pair(liq=100_000.0)])
    ctx = make_ctx(tmp_path, dex=dex)
    wid = _watch(ctx)
    assert run(poll.poll_once(ctx)) == 0  # baseline
    dex.pairs[0]["liquidity_usd"] = 60_000.0
    ctx.wdb._x("UPDATE watches SET last_check=0")
    assert run(poll.poll_once(ctx)) == 1
    job = ctx.wdb.one("SELECT payload FROM jobs WHERE kind='tg_dm'")
    assert "fell 40.0%" in json.loads(job["payload"])["text"]
    dex.pairs[0]["liquidity_usd"] = 30_000.0  # another 50% drop, but inside the cooldown
    ctx.wdb._x("UPDATE watches SET last_check=0")
    assert run(poll.poll_once(ctx)) == 0
    assert ctx.wdb.one("SELECT COUNT(*) AS n FROM watch_events WHERE watch_id=?", (wid,))["n"] == 2
    assert run(poll.poll_once(ctx)) == 0  # not due again yet (cadence)


class WalletRPC:
    def __init__(self):
        self.sigs = [{"signature": "old1"}]

    async def signatures(self, addr, limit):
        return self.sigs

    async def transaction(self, sig):
        return {
            "meta": {
                "preBalances": [100 * 10**9],
                "postBalances": [30 * 10**9],
                "preTokenBalances": [],
                "postTokenBalances": [],
                "err": None,
            },
            "transaction": {"signatures": [sig], "message": {"accountKeys": [WALLET], "instructions": []}},
            "blockTime": 1,
        }


def test_wallet_watch_silent_on_first_look_then_alerts(tmp_path):
    ctx = make_ctx(tmp_path, rpc=WalletRPC())
    _watch(ctx, "wallet_moves", WALLET, {"min_sol": 50.0})
    assert run(poll.poll_once(ctx)) == 0
    ctx.env.rpc.sigs = [{"signature": "new1"}, {"signature": "old1"}]
    ctx.wdb._x("UPDATE watches SET last_check=0")
    assert run(poll.poll_once(ctx)) == 1


def test_slots_owl_perk_and_global_cap(tmp_path):
    ctx = make_ctx(tmp_path)
    uid = ctx.wdb.user(tg_id="200")["id"]
    assert W.slots(ctx, uid) == ctx.wcfg.free_watches == 1
    _watch(ctx, uid=uid)
    assert not W.can_add(ctx, uid)[0]
    ctx.wdb._x("UPDATE users SET tier='inner', tier_expires_at=? WHERE id=?", (time.time() + 999, uid))
    familiars.choose(ctx.wdb, uid, "owl")
    assert W.slots(ctx, uid) == ctx.wcfg.inner_watches + 5 and W.can_add(ctx, uid)[0]
    ctx.wcfg.max_watches_global = 1
    assert "owls" in W.can_add(ctx, uid)[1]


def test_watch_reply_confirm_unlock_and_x(tmp_path):
    ctx = make_ctx(tmp_path, dex=FakeDex(search=[pair()]))
    uid = ctx.wdb.user(tg_id="300")["id"]
    r = run(surface.watch_reply(ctx, uid, "watch $MOSS liquidity drops 30%", "tg"))
    assert r.kind == "watch" and "30.0%" in r.text
    wid = int(r.buttons[0].data[3:])
    assert ctx.wdb.one("SELECT active FROM watches WHERE id=?", (wid,))["active"] == 0
    assert "is set" in surface.confirm(ctx, uid, wid)
    assert surface.confirm(ctx, ctx.wdb.user(tg_id="999")["id"], wid) == "That watch is gone."  # not yours
    assert "liquidity falls" in surface.list_text(ctx, uid)
    assert run(surface.watch_reply(ctx, uid, "tell me about unlocks for $MOSS", "tg")).kind == "unavailable"
    assert "Telegram" in run(surface.watch_reply(ctx, uid, "watch $MOSS liquidity", "x")).text
    assert surface.remove(ctx, uid, wid) and "empty" in surface.list_text(ctx, uid)
