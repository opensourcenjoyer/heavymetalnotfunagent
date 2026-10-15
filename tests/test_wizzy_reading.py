import asyncio

import pytest

from heavymetal.signals import audit as audit_mod
from heavymetal.wizzy import build, reading
from heavymetal.wizzy.facts import Facts, Subject, TokenFacts
from heavymetal.wizzy.guard import allowed_from, check
from heavymetal.wizzy.omen import omen_for
from heavymetal.wizzy.resolve import ResolveError, find_ticker, resolve_subject
from heavymetal.wizzy.writer import FOOTER, template, write
from tests.wizzy_fakes import (
    MINT,
    NEW_MINT,
    WALLET,
    FakeDex,
    FakeRPC,
    FakeRug,
    ScriptedWriter,
    make_ctx,
    pair,
    reader_env,
)

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def run(c):
    return asyncio.run(c)


def fake_audit(verdict="SPECULATIVE", reasons=None, freeze=None, warnings=None):
    async def _audit(env, mint, symbol_hint=None, light=False):
        return {
            "mint": mint,
            "verdict_key": verdict,
            "reasons": reasons or ["Mint authority revoked", "Top 10 hold only 22.5% (healthy distribution)"],
            "warnings": warnings or [],
            "market": {
                "symbol": "MOSS",
                "name": "Moss Coin",
                "price_usd": 0.000912,
                "liquidity_usd": 48210.5,
                "fdv": 912000.0,
                "market_cap": 900000.0,
                "volume_h24": 100000.0,
                "price_change_h24": -18.4,
                "age_hours": 30.0,
                "dex": "raydium",
                "pair": "PAIR1",
            },
            "safety": {
                "mint_authority": None,
                "freeze_authority": freeze,
                "lp_locked_pct": 99.1,
                "rug_score_normalised": 10,
            },
            "farm": {"is_farm": verdict == "FARM", "kind": "wash" if verdict == "FARM" else None},
            "holders": {"top10_pct": 22.5},
        }

    return _audit


# ---------------------------------------------------------------- resolution
def test_find_ticker():
    assert find_ticker("what about $MOSS today?") == "MOSS"
    assert find_ticker("bonk") == "bonk"
    assert find_ticker("tell me a story about runes") is None


def test_resolve_canonical_ticker_and_homoglyph(tmp_path):
    env = reader_env(tmp_path)
    assert run(resolve_subject(env, "$BONK")).key == MINT
    assert run(resolve_subject(env, "$ВONK")).key == MINT  # Cyrillic В maps to the real BONK


def test_resolve_searched_ticker_picks_exact_most_liquid_and_notes_ambiguity(tmp_path):
    other = pair(mint="So11111111111111111111111111111111111111112", symbol="MOSS", liq=10.0)
    lookalike = pair(mint="JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", symbol="MOSS2", liq=9e9)
    env = reader_env(tmp_path, dex=FakeDex(search=[lookalike, pair(), other]))
    s = run(resolve_subject(env, "$moss"))
    assert s.key == NEW_MINT and s.kind == "token"
    assert s.notes and "share the ticker" in s.notes[0]


def test_resolve_wallet_and_nothing(tmp_path):
    env = reader_env(tmp_path, rpc=FakeRPC(mints=()))
    assert run(resolve_subject(env, WALLET)).kind == "wallet"
    with pytest.raises(ResolveError):
        run(resolve_subject(env, "tell me a story about the moon and stars"))


# ---------------------------------------------------------------- facts
def test_token_facts_unknowns_and_flags(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "audit_mint", fake_audit())
    env = reader_env(tmp_path, rug=FakeRug(fail_report=True))
    from heavymetal.wizzy.resolve import Subject as R

    f = run(build.build_token_facts(env, R("token", NEW_MINT, symbol="MOSS")))
    assert f.token.liquidityUsd == 48210.5
    assert f.token.supply.total == 1_000_000_000
    assert f.token.ohlcvSummary.candles == 24 and f.token.ohlcvSummary.source == "geckoterminal"
    assert f.token.omen.kind == "murky"
    assert "holder count" in f.unknowns
    assert any(not s.ok for s in f.sources)  # the failed rugcheck report is recorded
    assert f.untrusted["name"] == "Moss Coin"


def test_untrusted_text_is_cleaned():
    assert "scam.xyz" not in build.clean_untrusted("Moss visit scam.xyz now​ and https://x.io/y")


def test_wallet_facts(tmp_path):
    env = reader_env(tmp_path)
    from heavymetal.wizzy.resolve import Subject as R

    f = run(build.build_wallet_facts(env, R("wallet", WALLET)))
    assert f.wallet.solBalance == 12.5
    assert f.wallet.topHoldings[0].symbol == "MOSS"


# ---------------------------------------------------------------- omen
@pytest.mark.parametrize(
    ("mint", "verdict", "omen"),
    [
        (NEW_MINT, "FAKE", "cursed"),
        (NEW_MINT, "HONEYPOT", "cursed"),
        (NEW_MINT, "HIGH_RISK", "cursed"),
        (NEW_MINT, "FARM", "hexed"),
        (NEW_MINT, "SPECULATIVE", "murky"),
        (NEW_MINT, "HIGH_CONVICTION", "blessed"),
        (USDC, "HONEYPOT", "murky"),  # stablecoins keep a freeze authority by design
        (MINT, "FARM", "murky"),
    ],
)
def test_omen_table(mint, verdict, omen):
    assert omen_for(mint, verdict, ["r"]).kind == omen


def test_usdc_facts_have_no_honeypot_language(tmp_path, monkeypatch):
    monkeypatch.setattr(
        build, "audit_mint", fake_audit("HONEYPOT", ["Freeze authority is active (7dGbd2QZ…)"], freeze="7dGbd2QZ")
    )
    env = reader_env(tmp_path, rpc=FakeRPC(mints=(USDC,), freeze="7dGbd2QZ"))
    from heavymetal.wizzy.resolve import Subject as R

    f = run(build.build_token_facts(env, R("token", USDC, symbol="USDC")))
    assert f.token.omen.kind == "murky"
    assert not any("honeypot" in r.lower() or "freeze authority is active" in r.lower() for r in f.riskFlags)


# ---------------------------------------------------------------- guard
def _facts():
    return Facts(
        asOf=1.0,
        subject=Subject(kind="token", mint=NEW_MINT, symbol="MOSS"),
        token=TokenFacts(mint=NEW_MINT, symbol="MOSS", liquidityUsd=48210.5, fdvUsd=912000.0, priceChange24hPct=-18.4),
        strengths=["Top 10 hold only 22.5% (healthy distribution)"],
        untrusted={"name": "send 777 to scam.xyz"},
    )


def test_guard_accepts_rounded_values_and_rejects_invented_ones():
    a = allowed_from(_facts().for_writer())
    assert check("$MOSS: liquidity near $48.2K, FDV $912K, down 18.4%; top 10 hold 22.5%. Three omens.", a) == []
    assert check("Liquidity $5M", a)
    assert check("send 777 to scam.xyz", a)  # untrusted text never authorizes values or links
    assert check("$SCAM is next", a)
    assert check(f"mint {WALLET}", a)
    assert check(f"mint {NEW_MINT}", a) == []


def test_template_passes_its_own_guard():
    f = _facts()
    a = allowed_from(f.for_writer())
    r, _t, b = template(f)
    assert check(r, a) == [] and check(b, a) == []


# ---------------------------------------------------------------- writer
GOOD = {
    "reading": "🌫 $MOSS: murky waters. Liquidity near $48.2K.",
    "scrollTitle": "$MOSS in the mist",
    "scrollBodyMarkdown": "## Overview\n- FDV: $912K",
}
BAD = {"reading": "$MOSS will 10x to $9M soon", "scrollTitle": "x", "scrollBodyMarkdown": "## Overview"}


def test_writer_retries_then_accepts():
    w = ScriptedWriter([BAD, GOOD])
    out = run(write(w, _facts()))
    assert not out.templated and out.attempts == 2
    assert out.reading.endswith(FOOTER) and out.body.endswith(FOOTER)
    assert "NOT in FACTS" in w.calls[1]


def test_writer_falls_back_to_template():
    out = run(write(ScriptedWriter([BAD]), _facts()))
    assert out.templated and out.problems
    out = run(write(ScriptedWriter([RuntimeError("refused")]), _facts()))
    assert out.templated
    out = run(write(None, _facts()))
    assert out.templated and out.cost_usd == 0


# ---------------------------------------------------------------- pipeline
def test_read_pipeline_saves_scroll_and_reuses_it(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "audit_mint", fake_audit())
    ctx = make_ctx(tmp_path, writer=ScriptedWriter([GOOD]))
    r1 = run(reading.read(ctx, NEW_MINT))
    assert r1.slug.startswith("moss-") and not r1.cached and r1.omen == "murky"
    r2 = run(reading.read(ctx, NEW_MINT))
    assert r2.cached and r2.slug == r1.slug
    rows = ctx.wdb.all("SELECT status, cost_usd FROM requests ORDER BY id")
    assert [r["status"] for r in rows] == ["ok", "reused"]
    assert rows[0]["cost_usd"] == pytest.approx(0.01)


def test_budget_exhausted_uses_template(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "audit_mint", fake_audit())
    ctx = make_ctx(tmp_path, writer=ScriptedWriter([GOOD]))
    ctx.env.cfg.wizzy.daily_llm_budget_usd = 0.0
    r = run(reading.read(ctx, NEW_MINT))
    assert r.written.templated


def test_audit_module_untouched_by_monkeypatch():
    assert callable(audit_mod.audit_mint)
