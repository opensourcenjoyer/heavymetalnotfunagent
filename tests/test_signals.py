"""Farm filter, signal ledger, performance, backtest leak guards, FARM_BLOCK."""

import json
import time

from conftest import MINT, FakeDex, run

from heavymetal.config import Config
from heavymetal.data.helius import swaps_per_wallet
from heavymetal.review import release, review_trade
from heavymetal.signals import backtest as bt
from heavymetal.signals.farm import classify_farm, metrics_from
from heavymetal.signals.ledger import get_signal, mark, recent_verdict, record_signal
from heavymetal.signals.performance import performance, runners


def gt_pool(liq=100_000, vol=500_000, buys=2000, sells=1800, buyers=600, sellers=400, chg=12.0, dex="pumpswap", **kw):
    p = {
        "pool": "Pool111",
        "mint": kw.get("mint", "Mint111"),
        "symbol": kw.get("symbol", "MEME"),
        "dex": dex,
        "liquidity_usd": liq,
        "fdv": kw.get("fdv", 2_000_000),
        "price_usd": kw.get("price", 0.002),
        "volume": {"h24": vol, "h6": vol / 4},
        "price_change": {"h24": chg},
        "txns": {"h24": {"buys": buys, "sells": sells, "buyers": buyers, "sellers": sellers}},
    }
    p.update({k: v for k, v in kw.items() if k in ("quote_mint", "quote_symbol", "created_ts", "age_hours")})
    return p


BUY = {"input_mint": "SOL", "output_mint": MINT, "amount": 0.1}


def farm(**kw):
    return classify_farm(metrics_from(gt=gt_pool(**kw)), Config())


# ---------------------------------------------------------------- farm gates
def test_organic_pool_passes():
    r = farm()
    assert not r.is_farm and not r.reasons


def test_wash_gate():
    r = farm(liq=10_000, vol=4_000_000)
    assert r.is_farm and r.kind == "wash"
    assert "400x" in r.reasons[0]


def test_zero_reserve_gate_needs_wallets():
    r = farm(liq=None, vol=2_000_000, buyers=40, sellers=30)
    assert r.is_farm and r.kind == "zero_reserve"
    r2 = farm(liq=None, vol=2_000_000, buyers=0, sellers=0, buys=0, sells=0)
    assert not r2.is_farm and any("unverifiable" in w for w in r2.warnings)


def test_roundtrip_gate():
    r = farm(buys=60_000, sells=60_000, buyers=600, sellers=400)  # 120 swaps per wallet
    assert r.is_farm and r.kind == "roundtrip"


def test_feefarm_only_on_low_fee_venue():
    churn = {"buys": 10_000, "sells": 10_000, "buyers": 600, "sellers": 400}  # 20 swaps per wallet
    assert farm(dex="orca", **churn).kind == "feefarm"
    r = farm(dex="pumpswap", **churn)
    assert not r.is_farm and any("churn" in w for w in r.warnings)
    m = metrics_from(gt=gt_pool(dex="pumpswap", **churn), dune={"min_fee_tier": 0.0001})
    assert classify_farm(m, Config()).kind == "feefarm"


def test_thin_crowd_gate():
    r = farm(vol=200_000, buys=50, sells=40, buyers=8, sellers=6)
    assert r.is_farm and r.kind == "thin_crowd"


def test_flat_loop_gate():
    r = farm(liq=5_000, vol=900_000, chg=0.4, buys=5000, sells=5000, buyers=2000, sellers=2000)
    assert r.is_farm and r.kind == "flat_loop"


def test_manual_deny_list():
    cfg = Config()
    cfg.signals.deny_mints = ["Mint111"]
    assert classify_farm(metrics_from(gt=gt_pool()), cfg).kind == "manual"


def test_birdeye_and_helius_override_wallet_counts():
    m = metrics_from(gt=gt_pool(), birdeye={"unique_wallets_24h": 10, "trades_24h": 3000})
    assert m["wallets_source"] == "birdeye" and m["swaps_per_wallet"] == 300
    m = metrics_from(gt=gt_pool(), helius={"swaps_per_wallet_day": 42.0, "top_wallet_share": 0.5})
    assert m["swaps_per_wallet_source"] == "helius"
    r = classify_farm(m, Config())
    assert any("one wallet" in w for w in r.warnings)


def test_helius_swaps_per_wallet():
    txs = [{"feePayer": "A" if i % 4 else "B", "timestamp": 1000 + i * 36} for i in range(100)]  # 1h span
    r = swaps_per_wallet(txs)
    assert r["wallets"] == 2 and r["swaps_per_wallet"] == 50
    assert r["swaps_per_wallet_day"] > 1000
    assert r["top"][0]["wallet"] == "A"


# ---------------------------------------------------------------- review gate
class FarmDex(FakeDex):
    async def token_pairs(self, mint):
        p = (await super().token_pairs(mint))[0]
        p.update(volume={"h24": self.liq * 1000}, txns_h24={"buys": 100, "sells": 100}, pair="P1")
        return [p]


def test_review_blocks_farm_buys(make_env):
    env = make_env(liquidity_usd=50_000)
    env.dex = FarmDex(50_000)
    v = run(review_trade(env, "swap", BUY))
    assert v["verdict"] == "FARM_BLOCK"
    assert "wash" in v["reasons"][0]


def test_review_blocks_mint_flagged_farm_in_ledger(make_env):
    env = make_env()
    record_signal(env.db, {"mint": MINT, "verdict_key": "FARM", "market": {}, "reasons": ["wash"]}, "audit")
    v = run(review_trade(env, "swap", BUY))
    assert v["verdict"] == "FARM_BLOCK"


def test_farm_block_priority_below_fake_above_risk():
    assert release([("RISK_BLOCK", ""), ("FARM_BLOCK", "")]) == "FARM_BLOCK"
    assert release([("FARM_BLOCK", ""), ("FAKE_TOKEN_BLOCK", "")]) == "FAKE_TOKEN_BLOCK"


def test_review_allows_organic_buy(make_env):
    env = make_env()
    v = run(review_trade(env, "swap", BUY))
    assert v["verdict"] == "EXECUTE"


# ---------------------------------------------------------------- ledger
def audit(mint="M1", verdict="SPECULATIVE", fdv=100_000, liq=30_000, features=None):
    return {
        "mint": mint,
        "verdict_key": verdict,
        "reasons": ["x"],
        "market": {"symbol": mint, "fdv": fdv, "liquidity_usd": liq, "price_usd": 0.0001, "pair": "P" + mint},
        "features": features if features is not None else {"as_of": time.time(), "liquidity_usd": liq, "fdv": fdv},
    }


def test_first_call_only_and_verdict_now(make_env):
    db = make_env().db
    sid, new = record_signal(db, audit(fdv=100_000), "audit")
    sid2, new2 = record_signal(db, audit(verdict="FARM", fdv=900_000), "scanner")
    s = get_signal(db, sid)
    assert new and not new2 and sid == sid2
    assert s["fdv0"] == 100_000 and s["verdict"] == "SPECULATIVE" and s["verdict_now"] == "FARM"
    assert recent_verdict(db, "M1") == "FARM"


def test_milestones_liquidity_gate_once_and_never_deleted(make_env):
    db = make_env().db
    sid, _ = record_signal(db, audit(fdv=100_000), "audit")
    sig = get_signal(db, sid)
    assert mark(db, sig, 250_000, 10_000, 1)["milestones"] == []  # 2.5x but thin liquidity
    r = mark(db, get_signal(db, sid), 550_000, 40_000, 1)
    assert r["milestones"] == [2, 3, 5]  # not the first observation any more: every level logs
    assert mark(db, get_signal(db, sid), 120_000, 40_000, 1)["milestones"] == []  # pullback
    levels = [x["level"] for x in db.conn.execute("SELECT level FROM milestones WHERE signal_id=?", (sid,))]
    assert levels == [2, 3, 5]


def test_first_observation_logs_only_highest(make_env):
    db = make_env().db
    sid, _ = record_signal(db, audit(fdv=100_000), "audit")
    r = mark(db, get_signal(db, sid), 1_200_000, 50_000, 1)
    assert r["milestones"] == [10]
    row = db.conn.execute("SELECT first_observed FROM milestones WHERE signal_id=?", (sid,)).fetchone()
    assert row["first_observed"] == 1


def test_dead_and_rugged_status(make_env):
    db = make_env().db
    sid, _ = record_signal(db, audit("R", liq=50_000), "audit")
    assert mark(db, get_signal(db, sid), 90_000, 200, 1)["status"] == "rugged"
    sid2, _ = record_signal(db, audit("D", liq=3_000), "audit")
    assert mark(db, get_signal(db, sid2), 5_000, 2_000, 1)["status"] == "dead"  # < 0.1x


def _age(db, sid, hours):
    db.conn.execute("UPDATE signals SET ts=? WHERE id=?", (time.time() - hours * 3600, sid))
    db.conn.commit()


def test_performance_counts_only_matured_and_marks_thin(make_env):
    db = make_env().db
    a, _ = record_signal(db, audit("A"), "audit")
    b, _ = record_signal(db, audit("B"), "audit")
    _age(db, a, 30)
    _age(db, b, 2)  # too young for the 24h window
    mark(db, get_signal(db, a), 300_000, 50_000, 1, ts=time.time() - 20 * 3600)
    perf = performance(db)
    row = perf["rows"][0]
    assert row["verdict"] == "SPECULATIVE" and row["n"] == 2
    assert row["n_24h"] == 1 and row["hit_24h"] == 1.0 and row["thin_24h"]
    assert row["hit_72h"] is None  # nothing matured: n/a, never zero


def test_runners_rank_and_liquidity_floor(make_env):
    db = make_env().db
    a, _ = record_signal(db, audit("A"), "audit")
    b, _ = record_signal(db, audit("B"), "audit")
    mark(db, get_signal(db, a), 300_000, 50_000, 1, chg_h1=5, chg_h24=40)
    mark(db, get_signal(db, b), 150_000, 5_000, 1)
    rows = runners(db, min_liq=25_000)
    assert [r["mint"] for r in rows] == ["A"]
    assert rows[0]["multiple"] == 3.0 and rows[0]["state"] == "running"


# ---------------------------------------------------------------- backtest leak guards
def test_backtest_guards(make_env):
    db = make_env().db
    ok_id, _ = record_signal(db, audit("OK", features={"as_of": time.time() - 100 * 3600, "fdv": 1}), "audit")
    late, _ = record_signal(db, audit("LATE", features={"as_of": time.time() + 3600, "fdv": 1}), "audit")
    young, _ = record_signal(db, audit("YOUNG"), "audit")
    _age(db, ok_id, 100)
    _age(db, late, 100)
    _age(db, young, 1)
    rows, guards = bt.dataset(db, horizon_h=72)
    assert [r["id"] for r in rows] == [ok_id]
    assert guards["features_after_signal"] == 1 and guards["immature"] == 1
    # a milestone stamped before the signal is a leak: dropped from the label
    db.conn.execute(
        "INSERT INTO milestones (signal_id, level, ts, fdv, first_observed) VALUES (?,?,?,?,0)",
        (ok_id, 2, time.time() - 200 * 3600, 1),
    )
    db.conn.commit()
    rows, guards = bt.dataset(db, horizon_h=72)
    assert guards["label_before_signal"] == 1 and rows[0]["y"] == 0


def test_backtest_insufficient_then_walk_forward(make_env):
    db = make_env().db
    assert bt.backtest(db)["status"] == "insufficient"
    for i in range(60):
        good = i % 3 == 0
        liq = 80_000 if good else 6_000
        sid, _ = record_signal(
            db,
            audit(
                f"T{i}",
                verdict="HIGH_CONVICTION" if good else "SPECULATIVE",
                liq=liq,
                features={"as_of": 0, "liquidity_usd": liq, "buy_ratio_h1": 0.8 if good else 0.4},
            ),
            "audit",
        )
        ts = time.time() - (200 - i) * 3600
        db.conn.execute("UPDATE signals SET ts=? WHERE id=?", (ts, sid))
        if good:
            db.conn.execute(
                "INSERT INTO milestones (signal_id, level, ts, fdv, first_observed) VALUES (?,?,?,?,0)",
                (sid, 2, ts + 3600, 1),
            )
    db.conn.commit()
    res = bt.backtest(db, horizon_h=72)
    assert res["status"] == "ok" and len(res["folds"]) == 4
    assert res["models"]["logit"]["auc"] >= 0.9
    assert res["models"]["rules"]["auc"] >= 0.9
    for f in res["folds"]:  # time-ordered: train strictly before test
        assert f["train"] > 0 and f["test"] > 0


def test_auc():
    assert bt.auc([0.9, 0.8, 0.1, 0.2], [1, 1, 0, 0]) == 1.0
    assert bt.auc([0.5, 0.5], [1, 0]) == 0.5
    assert bt.auc([0.5], [1]) is None


def test_token_audit_records_signal_and_wiki_refs(make_env, monkeypatch):
    from heavymetal.tools import analyze
    from heavymetal.tools.registry import execute

    env = make_env()

    class R:
        mint, symbol, name = MINT, "BONK", "Bonk"

        def to_dict(self):
            return {"mint": MINT}

    async def fake_resolve(env, target):
        return R()

    async def fake_audit(env, mint, symbol=None, light=False):
        a = audit(mint, verdict="FARM")
        a.update(
            verdict="HARD PASS / FARM", farm={"is_farm": True, "kind": "wash", "warnings": []}, safety={}, holders={}
        )
        return a

    monkeypatch.setattr(analyze, "resolve_target", fake_resolve)
    monkeypatch.setattr(analyze, "audit_mint", fake_audit)
    out = json.loads(run(execute(env, "token_audit", {"target": MINT})))
    assert out["verdict"] == "HARD PASS / FARM"
    assert out["signal"]["new"] is True
    assert out["wiki_refs"][0]["slug"] == "farms/wash-loops"
    assert "features" not in out
    assert get_signal(env.db, MINT)["verdict"] == "FARM"
