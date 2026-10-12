"""Trenches gates/sweep/ledger, launch ladders, Fear & Greed, wiki, connectors, GeckoTerminal parsing, scanner."""

import datetime as dt
import time

import pytest
from conftest import run
from test_signals import gt_pool

from heavymetal.config import Config
from heavymetal.data.connectors import missing, status
from heavymetal.data.geckoterminal import GeckoTerminal, normalize_pool
from heavymetal.kb.wiki import Wiki, refs_for_audit
from heavymetal.memory import DB
from heavymetal.trenches import fear_greed as fg
from heavymetal.trenches import pulse
from heavymetal.trenches.gates import gate_pool, is_equity
from heavymetal.trenches.launches import d1_and_top, ladders, upsert_launch

SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


@pytest.fixture
def db(tmp_path):
    return DB(tmp_path / "t.db")


# ---------------------------------------------------------------- gates
def test_gates():
    cfg = Config()
    assert (
        gate_pool(gt_pool(mint=SOL, symbol="SOL", price=150, quote_mint=USDC, quote_symbol="USDC"), cfg)[0] == "major"
    )
    assert gate_pool(gt_pool(fdv=900_000_000), cfg)[0] == "megacap"
    assert gate_pool(gt_pool(symbol="NVDAx", price=180.0), cfg)[0] == "equity"
    assert gate_pool(gt_pool(liq=1_000, vol=2_000_000), cfg)[0] == "wash"
    assert gate_pool(gt_pool(quote_mint=SOL, quote_symbol="SOL"), cfg)[0] is None


def test_meme_squatting_a_stock_ticker_stays_in():
    assert not is_equity("NVDAx", 0.00001)
    assert is_equity("TSLAx", 300)


class FakeGecko:
    def __init__(self, pools):
        self.pools = pools

    async def top_pools(self, pages=10):
        return self.pools

    async def ohlcv(self, *a, **k):
        return []


class FakeLlama:
    async def chain_dex_volume(self, chain="solana"):
        days = [((dt.date.today() - dt.timedelta(days=i)).isoformat(), 1_000_000.0) for i in range(30, 0, -1)]
        return {"days": days, "total24h": 1_000_000.0}


class FakeDexBatch:
    async def tokens_batch(self, mints):
        return {}


def sweep_env(db, pools):
    from types import SimpleNamespace

    return SimpleNamespace(
        cfg=Config(), db=db, gecko=FakeGecko(pools), llama=FakeLlama(), dex=FakeDexBatch(), dune=None, cluster="mainnet"
    )


def test_sweep_merges_tickers_counts_drops_and_top5(db):
    pools = [
        gt_pool(symbol="AAA", vol=300_000, mint="a1"),
        gt_pool(symbol="aaa", vol=100_000, mint="a2"),  # copycat / second pool: same ticker
        gt_pool(symbol="BBB", vol=200_000, mint="b"),
        *[gt_pool(symbol=f"T{i}", vol=10_000, mint=f"t{i}") for i in range(6)],
        gt_pool(symbol="WASH", liq=100, vol=900_000, mint="w"),
        gt_pool(symbol="BIG", fdv=5e9, vol=700_000, mint="big"),
    ]
    agg, _ = run(pulse.sweep(sweep_env(db, pools)))
    assert agg["smallcap_vol"] == 660_000
    assert agg["top5"][0] == {"symbol": "AAA", "vol": 400_000, "share": round(400_000 / 660_000, 4)}
    assert agg["trench_vol"] == 660_000 - (400_000 + 200_000 + 30_000)
    assert agg["drops"]["wash"] == {"n": 1, "vol": 900_000}
    assert agg["drops"]["megacap"]["n"] == 1
    assert agg["total_vol"] == 660_000 + 900_000 + 700_000
    assert agg["pace"] == 1.0


def test_bank_precedence_and_estimates(db):
    day = "2026-01-01"
    pulse.bank(db, day, {"source": "dune", "smallcap_vol": 500}, 1000)
    pulse.bank(db, day, {"source": "gt", "smallcap_vol": 999}, 1000)  # a sweep never overwrites dune
    assert db.conn.execute("SELECT smallcap_vol FROM trench_days WHERE day=?", (day,)).fetchone()[0] == 500
    n = pulse.backfill_estimates(db, [("2025-12-30", 2000.0), ("2025-12-31", 4000.0), (day, 9999.0)])
    assert n == 2  # measured day untouched
    rows = {r["day"]: r for r in pulse.series(db)}
    assert rows["2025-12-31"]["smallcap"] == 2000.0 and rows["2025-12-31"]["source"] == "est"  # share 0.5


def test_regime_and_ema():
    assert pulse.regime(list(range(1, 100)))["label"] == "hot"
    assert pulse.regime(list(range(100, 0, -1)))["label"] == "cold"
    assert pulse.regime([1, 2])["label"] == "n/a"
    assert pulse.ema([1, 1, 1], 7) == 1


def test_refresh_end_to_end(db):
    pulse._cache.clear()
    pools = [gt_pool(symbol=f"T{i}", vol=50_000 * (i + 1), mint=f"t{i}") for i in range(8)]
    p = run(pulse.refresh(sweep_env(db, pools), force=True))
    assert p["today"]["smallcap_vol"] == sum(50_000 * (i + 1) for i in range(8))
    assert p["fear_greed"]["index"] is None  # no scored launches yet: withheld
    assert p["fear_greed"]["arms"]["volume"] is not None
    assert "est" in p["sources"] and "gt" in p["sources"]


# ---------------------------------------------------------------- launches
def test_d1_close_and_wick_proof_top():
    t0 = 1_000_000
    candles = [{"ts": t0 + h * 3600, "close": 1 + h * 0.01, "volume": 1000} for h in range(24)]
    candles += [
        {"ts": t0 + 30 * 3600, "close": 50, "volume": 10},  # wick: no volume
        {"ts": t0 + 40 * 3600, "close": 5, "volume": 900},
    ]
    d1, top, _ = d1_and_top(candles, t0)
    assert d1 == pytest.approx(1.23) and top == 5


def test_ladders(db):
    now = time.time()
    for i in range(10):
        upsert_launch(
            db,
            {
                "pool": f"p{i}",
                "mint": f"m{i}",
                "symbol": f"S{i}",
                "created_ts": now - 3 * 86400,
                "price_usd": 1,
                "volume": {"h24": 50_000},
                "liquidity_usd": 10_000,
            },
            "test",
        )
        db.conn.execute(
            "UPDATE launches SET d1_close=1, last_price=?, top_price=? WHERE pool=?",
            (3 if i < 2 else 0.5, 12 if i < 5 else 1, f"p{i}"),
        )
    db.conn.commit()
    lad = ladders(db)
    assert lad["cohort"] == 10 and not lad["thin"]
    assert lad["hold"][2] == 0.2 and lad["hold"][5] == 0
    assert lad["ceiling"][10] == 0.5


# ---------------------------------------------------------------- fear & greed
def test_fg_score_is_monotonic_and_centered():
    assert fg.score(100, 100, "volume") == 50
    assert fg.score(300, 100, "volume") > fg.score(150, 100, "volume") > 50
    assert fg.score(50, 100, "volume") < 50
    assert fg.score(None, 100, "volume") is None
    assert fg.band(10)[0] == "EXTREME FEAR" and fg.band(50)[0] == "NEUTRAL" and fg.band(90)[0] == "EXTREME GREED"


def _series(vals, versions=None):
    return [{"day": f"d{i}", "smallcap": v, "version": (versions or [1] * len(vals))[i]} for i, v in enumerate(vals)]


def test_fg_withheld_below_min_tapes_and_weights():
    cfg = Config()
    ser = _series([700e6] * 20)
    res = fg.compute(cfg, ser, {"cohort": 3, "hold_depth": 0.06, "ceiling_depth": 0.22})
    assert res["index"] is None and res["arms"]["volume"] == 50
    res = fg.compute(cfg, ser, {"cohort": 20, "hold_depth": 0.06, "ceiling_depth": 0.22})
    assert res["index"] == 50


def test_fg_dead_market_stays_fear_even_with_momentum():
    cfg = Config()
    ser = _series([100e6] * 7 + [200e6] * 7)  # volume doubled week on week, but far under the normal
    res = fg.compute(cfg, ser, {"cohort": 20, "hold_depth": 0.01, "ceiling_depth": 0.05})
    assert res["arms"]["momentum"] > 80
    assert res["index"] < 45


def test_fg_momentum_sits_out_after_definition_change():
    ser = _series([100.0] * 10 + [200.0] * 10, versions=[1] * 10 + [2] * 10)
    ratio, why = fg.momentum_ratio(ser)
    assert ratio is None and "definition changed" in why
    ratio, why = fg.momentum_ratio(_series([100.0] * 7 + [150.0] * 7))
    assert ratio == pytest.approx(1.5) and why is None


# ---------------------------------------------------------------- wiki
def test_wiki_bundled_search_read_and_refs(tmp_path):
    w = Wiki(user=tmp_path / "wiki")
    assert len(w.pages) >= 20
    hits = w.search("zero reserve pumpswap")
    assert hits and hits[0]["slug"] in ("farms/zero-reserve-pools", "launchpads/pumpswap")
    assert w.read("wash-loops")["slug"] == "farms/wash-loops"
    assert w.read("rugs/cases/libra-2025")["verify"]
    for slug in w.pages:  # every [[link]] points at a real page
        for link in __import__("re").findall(r"\[\[([^\]]+)\]\]", w.pages[slug]["body"]):
            assert link in w.pages, f"{slug} links to missing {link}"


def test_wiki_note_and_validation(tmp_path):
    w = Wiki(user=tmp_path / "wiki")
    r = w.note("my-rules", "Entry rules", "never buy farms", tags="notes")
    assert r["slug"] == "notes/my-rules" and (tmp_path / "wiki/notes/my-rules.md").exists()
    assert w.search("farms never")[0]["origin"] in ("user", "bundled")
    with pytest.raises(ValueError):
        w.note("../../etc/passwd", "x", "y")


def test_refs_for_audit():
    refs = refs_for_audit(
        {
            "verdict_key": "FARM",
            "farm": {"kind": "feefarm"},
            "safety": {"is_token_2022": True},
            "market": {"dex": "pumpswap"},
            "holders": {"top10_pct": 60},
        }
    )
    slugs = [r["slug"] for r in refs]
    assert slugs[0] == "farms/fee-farming" and "rugs/token-2022-traps" in slugs and len(slugs) <= 4


# ---------------------------------------------------------------- connectors & keys
def test_connector_status_and_env_override(monkeypatch, tmp_path):
    from heavymetal import config as config_mod

    monkeypatch.setenv("HEAVYMETAL_HOME", str(tmp_path))
    monkeypatch.setenv("BIRDEYE_API_KEY", "be-secret-123456")
    cfg = config_mod.load()
    st = {s["name"]: s for s in status(cfg)}
    assert st["birdeye"]["configured"] and "secret" not in st["birdeye"]["value"]
    assert st["geckoterminal"]["keyless"]
    assert "dune" in missing(cfg) and "birdeye" not in missing(cfg)
    cfg.signals.deny_mints = ["X"]
    config_mod.save(cfg)
    assert config_mod.load().signals.deny_mints == ["X"]


# ---------------------------------------------------------------- geckoterminal
def test_normalize_pool():
    raw = {
        "attributes": {
            "address": "POOL",
            "name": "PULT / SOL",
            "base_token_price_usd": "0.00003",
            "fdv_usd": "3181964.0",
            "market_cap_usd": None,
            "reserve_in_usd": "340850.04",
            "pool_created_at": "2026-10-12T00:24:22Z",
            "volume_usd": {"h24": "105342048.3", "h6": "1"},
            "price_change_percentage": {"h24": "244.42"},
            "transactions": {"h24": {"buys": 48595, "sells": 44076, "buyers": 4222, "sellers": 788}},
        },
        "relationships": {
            "base_token": {"data": {"id": "solana_MINT"}},
            "quote_token": {"data": {"id": f"solana_{SOL}"}},
            "dex": {"data": {"id": "pumpswap"}},
        },
    }
    p = normalize_pool(raw, {"MINT": {"symbol": "PULT", "name": "Catapult"}})
    assert p["mint"] == "MINT" and p["symbol"] == "PULT" and p["quote_symbol"] == "SOL" and p["dex"] == "pumpswap"
    assert p["liquidity_usd"] == pytest.approx(340850.04) and p["market_cap"] is None
    assert p["txns"]["h24"]["buyers"] == 4222 and p["volume"]["h24"] > 1e8


def test_geckoterminal_retries_429():
    import httpx

    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"data": [], "included": []})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            g = GeckoTerminal(http)
            import heavymetal.data.geckoterminal as mod

            orig = mod.asyncio.sleep

            async def fast(_s):
                await orig(0)

            mod.asyncio.sleep = fast
            try:
                return await g.new_pools()
            finally:
                mod.asyncio.sleep = orig

    assert run(go()) == [] and calls["n"] == 2


# ---------------------------------------------------------------- scanner
def test_scanner_promotes_pending_and_marks(db, monkeypatch):
    from types import SimpleNamespace

    from heavymetal.signals.scanner import Scanner

    class Dex:
        async def tokens_batch(self, mints):
            return {
                m: {
                    "base": {"symbol": "NEW"},
                    "volume": {"h24": 60_000, "h1": 1000},
                    "liquidity_usd": 30_000,
                    "fdv": 300_000,
                    "price_usd": 1,
                    "price_change": {"h1": 5, "h24": 50},
                }
                for m in mints
            }

    env = SimpleNamespace(cfg=Config(), db=db, dex=Dex(), cluster="devnet")
    sc = Scanner(env)
    assert not sc.start() and "mainnet" in sc.last_error
    sc._add_pending("MintA", "NEW", "pump")
    sc._add_pending("MintB", "OLD", "pump")
    sc.pending["MintA"]["next"] = 0

    assert run(sc.promote_once()) == 1
    assert sc.queue.qsize() == 1 and "MintA" not in sc.pending and "MintB" in sc.pending  # B not due yet
    from heavymetal.signals.ledger import record_signal

    record_signal(
        db,
        {
            "mint": "MintA",
            "verdict_key": "SPECULATIVE",
            "reasons": [],
            "market": {"fdv": 100_000, "liquidity_usd": 30_000, "price_usd": 0.3},
        },
        "pump",
    )
    alerts = []
    sc.on_alert = lambda k, a: alerts.append(a)
    assert run(sc.mark_once())["marked"] == 1
    assert [a["level"] for a in alerts if a["kind"] == "milestone"] == [3]  # first observation: highest only
