from types import SimpleNamespace

import pytest

from heavymetal.memory import DB
from heavymetal.solana.fake_check import inspect_token_safety, normalize_ticker
from heavymetal.solana.positions import compute_targets, evaluate_open_positions, track_new_position
from heavymetal.solana.resolver import extract_address_from_text, resolve_target

REAL_BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
FAKE_BONK = "FakeBonk111111111111111111111111111111111111"
PAIR_ADDR = "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"


def test_extract_address_from_various_urls():
    # DexScreener URL
    addr, url = extract_address_from_text(f"https://dexscreener.com/solana/{PAIR_ADDR}")
    assert addr == PAIR_ADDR and url is not None

    # pump.fun URL
    pump_url = "https://pump.fun/coin/9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump"
    addr, url = extract_address_from_text(pump_url)
    assert addr == "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump"

    # Raw address
    addr, url = extract_address_from_text(REAL_BONK)
    assert addr == REAL_BONK and url is None

    # Invalid input
    addr, url = extract_address_from_text("not a solana address")
    assert addr is None


def test_normalize_ticker():
    # Zero-width spaces stripped
    zw = "B\u200bO\u200cN\ufeffK"
    assert normalize_ticker(zw) == "BONK"

    # Cyrillic A homoglyph normalized to ASCII A
    cyrillic_sol = "SОL"  # Cyrillic О (U+041E)
    assert normalize_ticker(cyrillic_sol) == "SOL"

    assert normalize_ticker(" $wif ") == "WIF"


def test_compute_targets():
    entry = 0.05
    tp, sl = compute_targets(entry, tp_multiple=2.0, sl_pct=30.0)
    assert tp == 0.10
    assert sl == 0.035

    tp, sl = compute_targets(entry, tp_multiple=3.0, sl_pct=50.0)
    assert tp == 0.15
    assert sl == 0.025


@pytest.mark.anyio
async def test_resolve_target_mint_and_pair():
    class MockRPC:
        async def mint_info(self, addr):
            if addr == REAL_BONK:
                return {"decimals": 5, "supply": 1000}
            raise RuntimeError("not a mint")

    class MockDex:
        async def token_pairs(self, addr):
            return [{"base": {"symbol": "BONK", "name": "Bonk"}, "pair": "Pair123", "dex": "raydium"}]

        async def pair(self, addr):
            if addr == PAIR_ADDR:
                return {"base": {"address": REAL_BONK, "symbol": "BONK", "name": "Bonk"}, "dex": "raydium"}
            return None

    env = SimpleNamespace(rpc=MockRPC(), dex=MockDex())

    # Direct mint resolution
    res_mint = await resolve_target(env, f"https://dexscreener.com/solana/{REAL_BONK}")
    assert res_mint.kind == "mint" and res_mint.mint == REAL_BONK

    # Pair resolution to base mint
    res_pair = await resolve_target(env, f"https://dexscreener.com/solana/{PAIR_ADDR}")
    assert res_pair.kind == "pair" and res_pair.mint == REAL_BONK


@pytest.mark.anyio
async def test_fake_check_canonical_spoof():
    class MockRPC:
        async def call(self, method, params):
            return {"value": {"data": {"parsed": {"info": {"freezeAuthority": None, "mintAuthority": None}}}}}

    env = SimpleNamespace(rpc=MockRPC())

    # Genuine BONK -> SAFE
    real = await inspect_token_safety(env, REAL_BONK, "BONK")
    assert not real.is_fake
    assert not real.canonical_spoof

    # Fake BONK mint -> FAKE_BLOCKED
    fake = await inspect_token_safety(env, FAKE_BONK, "BONK")
    assert fake.is_fake
    assert fake.canonical_spoof
    assert "Impersonating $BONK" in fake.reasons[0]


@pytest.mark.anyio
async def test_position_tracking_and_evaluation(tmp_path):
    db = DB(tmp_path / "pos.db")

    class MockDex:
        async def token_pairs(self, mint):
            # Return current price = $0.12 (entry was $0.05, so +140%, hits 2x TP)
            return [{"price_usd": 0.12}]

    env = SimpleNamespace(db=db, dex=MockDex(), session_id="test_s")

    # Track new position
    pos = await track_new_position(
        env=env,
        mint=REAL_BONK,
        symbol="BONK",
        sol_amount=0.1,
        entry_price_usd=0.05,
        tp_multiple=2.0,
        sl_pct=30.0,
    )
    assert pos["status"] == "OPEN"
    assert pos["tp_price_usd"] == 0.10
    assert pos["sl_price_usd"] == 0.035

    # Evaluate live status
    evaluated = await evaluate_open_positions(env)
    assert len(evaluated) == 1
    p0 = evaluated[0]
    assert p0["current_price_usd"] == 0.12
    assert p0["pnl_pct"] == 140.0
    assert p0["action_trigger"] == "TRIGGER_TP"
