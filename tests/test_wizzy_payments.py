import asyncio
import time

import pytest
from aiogram import Bot
from aiogram.methods import AnswerPreCheckoutQuery
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from heavymetal.wizzy import familiars, limits, scrolls
from heavymetal.wizzy.bots import tg
from heavymetal.wizzy.payments import entitlements as ent
from heavymetal.wizzy.payments import solana_pay, x402
from heavymetal.wizzy.web import app as app_mod
from tests.wizzy_fakes import make_ctx

PAY_TO = "Payee1111111111111111111111111111111111111"
REF = "Ref11111111111111111111111111111111111111111"


def run(c):
    return asyncio.run(c)


def make_inner(ctx, uid, days=30):
    ctx.wdb._x("UPDATE users SET tier='inner', tier_expires_at=? WHERE id=?", (time.time() + days * 86400, uid))


# ---------------------------------------------------------------- entitlements
def test_tokens_tamper_and_expiry(tmp_path):
    ctx = make_ctx(tmp_path)
    t = ent.scroll_token(ctx.wdb, "moss-1")
    assert ent.verify(ctx.wdb, t).startswith("s|moss-1|")
    assert ent.verify(ctx.wdb, t[:-1] + ("0" if t[-1] != "0" else "1")) is None
    old = ent.sign(ctx.wdb, f"u|5|{time.time() - 1:.0f}")
    assert ent.user_from_token(ctx.wdb, old) is None
    assert ent.user_from_token(ctx.wdb, ent.user_token(ctx.wdb, 5)) == 5


def test_scroll_access_cookie_inner_and_link(tmp_path):
    ctx = make_ctx(tmp_path)
    uid = ctx.wdb.user(tg_id="1")["id"]
    assert ent.scroll_access(ctx.wdb, {}, {}, "a")[0] is False
    ck = {ent.SCROLL_COOKIE_PREFIX + "a": ent.scroll_token(ctx.wdb, "a")}
    assert ent.scroll_access(ctx.wdb, ck, {}, "a") == (True, None)
    assert ent.scroll_access(ctx.wdb, ck, {}, "b")[0] is False  # a cookie unlocks only its own scroll
    k = ent.inner_token(ctx.wdb, uid)
    assert ent.scroll_access(ctx.wdb, {}, {"k": k}, "b")[0] is False  # token valid but user not inner
    make_inner(ctx, uid)
    ok, grant = ent.scroll_access(ctx.wdb, {}, {"k": k}, "b")
    assert ok and grant == (ent.INNER_COOKIE, k)


def test_grant_inner_blocks_replay_and_extends(tmp_path):
    ctx = make_ctx(tmp_path)
    uid = ctx.wdb.user(tg_id="2")["id"]
    assert ent.grant_inner(ctx.wdb, uid, days=30, method="stars", tx_key="stars:1", amount=500)
    first = ctx.wdb.one("SELECT tier_expires_at FROM users WHERE id=?", (uid,))["tier_expires_at"]
    assert not ent.grant_inner(ctx.wdb, uid, days=30, method="stars", tx_key="stars:1", amount=500)
    assert ent.grant_inner(ctx.wdb, uid, days=30, method="stars", tx_key="stars:2", amount=500)
    second = ctx.wdb.one("SELECT tier_expires_at FROM users WHERE id=?", (uid,))["tier_expires_at"]
    assert second == pytest.approx(first + 30 * 86400, abs=5)


# ---------------------------------------------------------------- x402 flow
class FakeX402(BaseHTTPMiddleware):
    """Stands in for the x402 middleware: /pay/* needs a payment header."""

    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/pay/") and "PAYMENT-SIGNATURE" not in request.headers:
            return Response("payment required", status_code=402)
        return await call_next(request)


def test_x402_purchase_unlocks_once(tmp_path, monkeypatch):
    ctx = make_ctx(tmp_path)
    ctx.wcfg.pay_to = PAY_TO
    monkeypatch.setattr(app_mod, "WEB_HOOKS", [lambda a, c: x402.install(a, c, middleware=FakeX402)])
    slug = scrolls.save(
        ctx.wdb,
        label="m",
        kind="token",
        title="T",
        reading="r",
        body_md="## Risks\n- PAID-BODY",
        omen=None,
        subject_id=None,
        request_id=None,
    )
    client = TestClient(app_mod.create_app(ctx, paywall=x402.make_paywall(ctx)))
    r = client.get(f"/s/{slug}/full")
    assert r.status_code == 402 and "PAID-BODY" not in r.text and f"/pay/s/{slug}" in r.text
    assert client.get(f"/pay/s/{slug}").status_code == 402
    paid = client.get(f"/pay/s/{slug}", headers={"PAYMENT-SIGNATURE": "sig-abc"})
    assert paid.status_code == 200 and "PAID-BODY" in paid.text
    again = client.get(f"/s/{slug}/full")  # the cookie unlocks it without paying again
    assert again.status_code == 200 and "PAID-BODY" in again.text
    rows = ctx.wdb.all("SELECT method, tx_sig FROM entitlements")
    assert len(rows) == 1 and rows[0]["method"] == "x402"


def test_x402_not_installed_without_pay_to(tmp_path, monkeypatch):
    ctx = make_ctx(tmp_path)
    monkeypatch.setattr(app_mod, "WEB_HOOKS", [x402.install])
    client = TestClient(app_mod.create_app(ctx))
    assert client.get("/pay/s/x").status_code == 404


def test_x402_middleware_args_build(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.wcfg.pay_to = PAY_TO
    args = x402.build_middleware_args(ctx)
    assert "GET /pay/s/:slug" in args["routes"] and args["paywall_config"].testnet is True


# ---------------------------------------------------------------- solana pay
def tx(reference=REF, owner=PAY_TO, mint=solana_pay.USDC_MINT, pre="1", post="10", err=None):
    return {
        "meta": {
            "err": err,
            "preTokenBalances": [{"mint": mint, "owner": owner, "uiTokenAmount": {"uiAmountString": pre}}],
            "postTokenBalances": [{"mint": mint, "owner": owner, "uiTokenAmount": {"uiAmountString": post}}],
        },
        "transaction": {"message": {"accountKeys": [{"pubkey": "Payer"}, {"pubkey": reference}]}},
    }


@pytest.mark.parametrize(
    ("t", "ok"),
    [
        (tx(), True),
        (tx(mint="FakeUSDC111"), False),
        (tx(owner="SomeoneElse"), False),
        (tx(post="9.5"), False),
        (tx(err={"InstructionError": [0, "x"]}), False),
        (tx(reference="OtherRef"), False),
        (None, False),
    ],
)
def test_check_tx(t, ok):
    assert solana_pay.check_tx(t, reference=REF, pay_to=PAY_TO, amount=9.0) is ok


class FakeRPC:
    def __init__(self, txs):
        self.txs = txs

    async def call(self, method, params):
        if method == "getSignaturesForAddress":
            return [{"signature": s, "err": None} for s in self.txs]
        assert params[1]["commitment"] == "finalized"
        return self.txs[params[0]]


def test_settle_order_grants_once_and_blocks_replay(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.wcfg.pay_to = PAY_TO
    ctx.wcfg.inner_price_usdc = 9.0
    a = ctx.wdb.user(tg_id="a")["id"]
    b = ctx.wdb.user(tg_id="b")["id"]
    ref1 = solana_pay.new_order(ctx.wdb, a, 9.0)
    ctx.env.rpc = FakeRPC({"SIG1": tx(reference=ref1)})
    assert run(solana_pay.settle_order(ctx, ref1)) == "paid"
    assert ctx.wdb.tier(a) == "inner"
    assert run(solana_pay.settle_order(ctx, ref1)) == "paid"  # idempotent
    # the same signature can't buy a second membership
    ref2 = solana_pay.new_order(ctx.wdb, b, 9.0)
    ctx.env.rpc = FakeRPC({"SIG1": tx(reference=ref2)})
    assert run(solana_pay.settle_order(ctx, ref2)) == "open"
    assert ctx.wdb.tier(b) == "free"
    assert "spl-token=" + solana_pay.USDC_MINT in solana_pay.pay_url(PAY_TO, 9.0, ref1)


# ---------------------------------------------------------------- familiars
def test_familiar_needs_inner_and_sets_perk(tmp_path):
    ctx = make_ctx(tmp_path)
    uid = ctx.wdb.user(tg_id="f")["id"]
    assert familiars.choose(ctx.wdb, uid, "raven") is None
    make_inner(ctx, uid)
    assert familiars.choose(ctx.wdb, uid, "raven").flag == "extra_readings_hour"
    assert limits.reading_quota(ctx, uid) == ctx.wcfg.inner_readings_per_hour + 5
    familiars.choose(ctx.wdb, uid, "owl")
    assert limits.perk(ctx.wdb, uid, "extra_readings_hour") == 0 and limits.perk(ctx.wdb, uid, "watch_slots") == 5
    assert familiars.users_with_perk(ctx.wdb, "watch_slots") == [uid]


# ---------------------------------------------------------------- telegram stars
def test_stars_checkout_and_payment(tmp_path, monkeypatch):
    ctx = make_ctx(tmp_path)
    sent = []

    async def fake_call(self, method, request_timeout=None):
        sent.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", fake_call)
    bot, dp = tg.build(ctx, token="42:TEST-TOKEN")
    uid = ctx.wdb.user(tg_id="77")["id"]
    who = {"id": 77, "is_bot": False, "first_name": "S"}
    pre = {
        "update_id": 1,
        "pre_checkout_query": {
            "id": "q1",
            "from": who,
            "currency": "XTR",
            "total_amount": ctx.wcfg.inner_price_stars,
            "invoice_payload": f"inner:{uid}",
        },
    }
    run(tg.feed_webhook(bot, dp, "s", "s", pre))
    assert next(m for m in sent if isinstance(m, AnswerPreCheckoutQuery)).ok is True
    bad = {**pre, "update_id": 2, "pre_checkout_query": {**pre["pre_checkout_query"], "id": "q2", "total_amount": 1}}
    run(tg.feed_webhook(bot, dp, "s", "s", bad))
    assert [m for m in sent if isinstance(m, AnswerPreCheckoutQuery)][1].ok is False

    def paid(n):
        return {
            "update_id": 10 + n,
            "message": {
                "message_id": n,
                "date": 1700000000,
                "chat": {"id": 77, "type": "private"},
                "from": who,
                "successful_payment": {
                    "currency": "XTR",
                    "total_amount": ctx.wcfg.inner_price_stars,
                    "invoice_payload": f"inner:{uid}",
                    "telegram_payment_charge_id": "charge-1",
                    "provider_payment_charge_id": "",
                },
            },
        }

    run(tg.feed_webhook(bot, dp, "s", "s", paid(1)))
    assert ctx.wdb.tier(uid) == "inner"
    run(tg.feed_webhook(bot, dp, "s", "s", paid(2)))  # Telegram retry: same charge id
    assert ctx.wdb.one("SELECT COUNT(*) AS n FROM entitlements")["n"] == 1
