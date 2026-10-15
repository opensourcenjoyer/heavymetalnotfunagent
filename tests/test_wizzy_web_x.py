import asyncio

from fastapi.testclient import TestClient

from heavymetal.wizzy import jobs, og, scrolls
from heavymetal.wizzy.bots import x as xmod
from heavymetal.wizzy.bots.core import Reply
from heavymetal.wizzy.web.app import create_app
from heavymetal.wizzy.web.pages import section
from tests.wizzy_fakes import make_ctx

BODY = "## Overview\n- Omen: murky\n## Tokenomics\n- SECRET-PAID-LINE FDV: $912K\n## Risks\n- none"


def run(c):
    return asyncio.run(c)


def _scroll(ctx, paywalled=True):
    return scrolls.save(
        ctx.wdb,
        label="MOSS",
        kind="token",
        title="$MOSS in the mist",
        reading="🌫 $MOSS: murky.",
        body_md=BODY,
        omen="murky",
        subject_id=None,
        request_id=None,
        paywalled=paywalled,
        price_usdc=0.25,
        chart_urls=["https://quickchart.io/chart?c=x"],
    )


def test_slug_and_section():
    assert scrolls.make_slug("$MOSS Coin!").startswith("moss-coin-")
    assert "SECRET" not in section(BODY, "Overview") and "Omen: murky" in section(BODY, "Overview")


def test_pages_public_preview_hides_paid_body(tmp_path, monkeypatch):
    from heavymetal.wizzy.web import app as app_mod

    monkeypatch.setattr(app_mod, "WEB_HOOKS", [])
    ctx = make_ctx(tmp_path)
    ctx.wcfg.pay_to = "Payee1111111111111111111111111111111111111"

    async def deny(ctx_, request, s):
        from fastapi import Response

        return Response("pay me", status_code=402)

    slug = _scroll(ctx)
    client = TestClient(create_app(ctx, paywall=deny))
    assert client.get("/healthz").json() == {"ok": True}
    assert "$MOSS in the mist" in client.get("/").text
    page = client.get(f"/s/{slug}")
    assert page.status_code == 200 and "SECRET-PAID-LINE" not in page.text
    assert "og:image" in page.text and "Unlock the full scroll" in page.text
    assert client.get(f"/s/{slug}/full").status_code == 402
    img = client.get(f"/og/{slug}.png")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert client.get("/s/nope").status_code == 404


def test_full_scroll_free_without_paywall_and_escapes_html(tmp_path):
    ctx = make_ctx(tmp_path)
    slug = scrolls.save(
        ctx.wdb,
        label="X",
        kind="token",
        title="<script>alert(1)</script>",
        reading="hi",
        body_md="## Overview\n<img src=x onerror=alert(1)>",
        omen=None,
        subject_id=None,
        request_id=None,
    )
    client = TestClient(create_app(ctx))
    full = client.get(f"/s/{slug}/full").text
    assert "<script>alert(1)</script>" not in full and "<img src=x" not in full


def test_tg_webhook_rejects_bad_secret(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.cfg.keys.telegram_webhook_secret = "right"

    class Dummy:
        pass

    client = TestClient(create_app(ctx, bot=Dummy(), dp=Dummy()))
    r = client.post("/tg/webhook", json={"update_id": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"})
    assert r.status_code == 401
    assert TestClient(create_app(ctx)).post("/tg/webhook", json={}).status_code == 404


def test_og_render_is_png():
    assert og.render("A very long title " * 8, "blessed", "sub").startswith(b"\x89PNG")


# ---------------------------------------------------------------- X
def test_render_x_fits_one_post():
    long = " ".join(["The runes whisper of thin liquidity and crowded holders."] * 10)
    out = xmod.render_x(Reply("reading", text=long, url="https://wizzy.example/s/moss-abc"))
    assert xmod._visible_len(out) <= 280 and "https://wizzy.example/s/moss-abc" in out and "NFA" in out


class FakeX:
    user_id = "999"

    def __init__(self, tweets):
        self.tweets = tweets
        self.since = []
        self.replies = []

    async def mentions(self, since_id):
        self.since.append(since_id)
        return [t for t in self.tweets if not since_id or int(t["id"]) > int(since_id)]

    async def reply(self, text, in_reply_to):
        self.replies.append((in_reply_to, text))
        return f"r{in_reply_to}"


def tweet(i, author="a1", conv="c1", text="@wizzy what is a bonding curve"):
    return {"id": str(i), "text": text, "author_id": author, "conversation_id": conv}


def test_poll_once_queues_dedupes_and_persists_since_id(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.wcfg.x_reply_delay_s = 0
    fx = FakeX([tweet(10), tweet(11, author="999"), tweet(12, author="a2", conv="c2")])
    assert run(xmod.poll_once(ctx, fx)) == 2  # own post skipped
    assert run(xmod.poll_once(ctx, fx)) == 0
    assert fx.since == [None, "12"]
    ctx.wdb._x("UPDATE jobs SET run_after=0")
    handlers = {"x_reply": lambda p: xmod.handle_reply_job(ctx, fx, p)}
    assert run(jobs.run_once(ctx.wdb, handlers)) == 2
    assert {r[0] for r in fx.replies} == {"10", "12"}
    assert all(xmod._visible_len(t) <= 280 for _, t in fx.replies)
    # a second mention from the same user in the same thread is ignored
    fx.tweets.append(tweet(13))
    assert run(xmod.poll_once(ctx, fx)) == 0


def test_x_daily_cap(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.wcfg.x_daily_reply_cap = 1
    fx = FakeX([tweet(1, author="a"), tweet(2, author="b", conv="c2")])
    assert run(xmod.poll_once(ctx, fx)) == 1


def test_x_chitchat_is_not_posted(tmp_path):
    ctx = make_ctx(tmp_path)
    fx = FakeX([])
    out = run(xmod.handle_reply_job(ctx, fx, tweet(5, text="@wizzy gm")))
    assert out == {"skipped": "chitchat"} and fx.replies == []
