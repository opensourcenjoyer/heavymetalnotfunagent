import asyncio
import time

import pytest
from aiogram import Bot
from aiogram.methods import AnswerCallbackQuery, SendMessage

from heavymetal.wizzy import apprentice, jobs, limits
from heavymetal.wizzy.bots import core, tg
from heavymetal.wizzy.router import rules
from tests.wizzy_fakes import make_ctx


def run(c):
    return asyncio.run(c)


# ---------------------------------------------------------------- router
@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("buy 0.5 sol of $BONK", "trade_request"),
        ("can you ape into this 9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin", "trade_request"),
        ("warn me if JUP's top holders move", "watch"),
        ("do my wallet tarot Hx4MLyVMwb3VPYA9EDfT1CbMCiNqtHgMyQXnVM39Hw6x", "tarot"),
        ("scry $MOSS", "scry"),
        ("is this a rug 9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin", "scry"),
        ("$WIF", "token"),
        ("BONK", "token"),
        ("https://dexscreener.com/solana/abc", "token"),
        ("what is FDV?", "lesson"),
        ("what's the hottest narrative right now", "narrative"),
        ("gm", "chitchat"),
    ],
)
def test_router_rules(text, kind):
    assert rules(text).kind == kind


def test_router_leaves_open_questions_to_the_model():
    assert rules("tell me something mysterious about the trenches tonight") is None


# ---------------------------------------------------------------- limits
def test_rate_limit_window(tmp_path):
    ctx = make_ctx(tmp_path)
    t0 = 1000.0
    assert all(limits.hit(ctx.wdb, "u1", "b", 3, 60, now=t0 + i).allowed for i in range(3))
    v = limits.hit(ctx.wdb, "u1", "b", 3, 60, now=t0 + 10)
    assert not v.allowed and 40 <= v.retry_after_s <= 51
    assert limits.hit(ctx.wdb, "u1", "b", 3, 60, now=t0 + 61).allowed


def test_reading_quota_tier_and_perk(tmp_path):
    ctx = make_ctx(tmp_path)
    uid = ctx.wdb.user(tg_id="1")["id"]
    assert limits.reading_quota(ctx, uid) == ctx.wcfg.free_readings_per_hour
    ctx.wdb._x("INSERT INTO perks(user_id, flag, value) VALUES(?, 'extra_readings_hour', 5)", (uid,))
    assert limits.reading_quota(ctx, uid) == ctx.wcfg.free_readings_per_hour  # perks need the Inner Circle
    ctx.wdb._x("UPDATE users SET tier='inner', tier_expires_at=? WHERE id=?", (time.time() + 99, uid))
    assert limits.reading_quota(ctx, uid) == ctx.wcfg.inner_readings_per_hour + 5


def test_kill_switch(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.wcfg.enabled = False
    assert not limits.check_reading(ctx, 1, "tg").allowed


# ---------------------------------------------------------------- jobs
def test_jobs_dedupe_retry_and_done(tmp_path):
    ctx = make_ctx(tmp_path)
    assert jobs.enqueue(ctx.wdb, "x_reply", {"n": 1}, dedupe_key="t1")
    assert jobs.enqueue(ctx.wdb, "x_reply", {"n": 1}, dedupe_key="t1") is None
    calls = []

    async def flaky(p):
        calls.append(p)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return "ok"

    assert run(jobs.run_once(ctx.wdb, {"x_reply": flaky})) == 0
    row = ctx.wdb.one("SELECT status, attempts, last_error FROM jobs")
    assert row["status"] == "queued" and row["attempts"] == 1 and "boom" in row["last_error"]
    ctx.wdb._x("UPDATE jobs SET run_after=0")
    assert run(jobs.run_once(ctx.wdb, {"x_reply": flaky})) == 1
    assert ctx.wdb.one("SELECT status FROM jobs")["status"] == "done"


def test_jobs_recover_stale(tmp_path):
    ctx = make_ctx(tmp_path)
    jobs.enqueue(ctx.wdb, "k", {})
    jobs.claim(ctx.wdb)
    ctx.wdb._x("UPDATE jobs SET updated_at=0")
    assert jobs.recover_stale(ctx.wdb) == 1


# ---------------------------------------------------------------- apprentice
def test_lessons_and_quizzes_parse():
    ls = apprentice.lessons()
    assert len(ls) == 10 and ls[0].slug == "lessons/liquidity"
    assert all(x.quiz and all(0 <= q.answer < len(q.options) for q in x.quiz) for x in ls)
    assert "```quiz" not in ls[0].body


def test_ranks_progress_and_archmage(tmp_path):
    ctx = make_ctx(tmp_path)
    uid = ctx.wdb.user(tg_id="7")["id"]
    assert apprentice.rank(ctx.wdb, uid).name == "Apprentice"
    ls = apprentice.lessons()
    assert not apprentice.record_quiz(ctx.wdb, uid, ls[0].slug, 0, 2)
    for x in ls[:3]:
        assert apprentice.record_quiz(ctx.wdb, uid, x.slug, 2, 3)
    r = apprentice.rank(ctx.wdb, uid)
    assert r.name == "Adept" and r.next_name == "Conjurer" and r.needed == 3
    assert apprentice.next_lesson(ctx.wdb, uid).slug == ls[3].slug
    for x in ls:
        apprentice.record_quiz(ctx.wdb, uid, x.slug, len(x.quiz), len(x.quiz))
    assert apprentice.rank(ctx.wdb, uid).name == "Archmage"


def test_lesson_suggestion():
    from heavymetal.wizzy.facts import Authorities, Facts, Subject, TokenFacts

    f = Facts(asOf=1, subject=Subject(kind="token"), token=TokenFacts(mint="m", authorities=Authorities(freeze="x")))
    assert apprentice.suggest_for(f).slug == "lessons/authorities"


# ---------------------------------------------------------------- core
def test_core_trade_and_chitchat_and_lesson(tmp_path):
    ctx = make_ctx(tmp_path)
    assert run(core.handle_text(ctx, 1, "sell all my $BONK now", surface="tg")).text == core.TRADE_LINE
    assert run(core.handle_text(ctx, 1, "gm", surface="tg")).kind == "chitchat"
    r = run(core.handle_text(ctx, 1, "what is a bonding curve", surface="tg"))
    assert r.kind == "lesson" and r.lesson.slug == "lessons/bonding-curves"


def test_core_limited_reading(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.wcfg.free_readings_per_hour = 0
    r = run(core.handle_text(ctx, 1, "$WIF", surface="tg"))
    assert r.kind == "limited"


def test_chat_flood_guard_goes_silent(tmp_path):
    ctx = make_ctx(tmp_path)
    for _ in range(20):
        run(core.handle_text(ctx, 1, "gm", surface="tg", chat_key="c1"))
    assert run(core.handle_text(ctx, 1, "gm", surface="tg", chat_key="c1")) is None


# ---------------------------------------------------------------- telegram
def test_webhook_secret_is_constant_time_and_required():
    assert tg.verify_secret("s3cret", "s3cret")
    assert not tg.verify_secret("s3cret", "nope")
    assert not tg.verify_secret("", "")


def _update(uid, text, chat_type="private", chat_id=None, update_id=1):
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 1700000000,
            "chat": {"id": chat_id or uid, "type": chat_type},
            "from": {"id": uid, "is_bot": False, "first_name": "W"},
            "text": text,
            "entities": [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
            if text.startswith("/")
            else [],
        },
    }


@pytest.fixture
def tg_harness(tmp_path, monkeypatch):
    ctx = make_ctx(tmp_path)
    sent = []

    async def fake_call(self, method, request_timeout=None):
        sent.append(method)
        if method.__class__.__name__ == "GetMe":
            from aiogram.types import User

            return User(id=42, is_bot=True, first_name="Wizzy", username="wizzybot")
        return True

    monkeypatch.setattr(Bot, "__call__", fake_call)
    bot, dp = tg.build(ctx, token="42:TEST-TOKEN")
    return ctx, bot, dp, sent


def test_tg_start_trade_and_group_silence(tg_harness):
    _ctx, bot, dp, sent = tg_harness
    assert not run(tg.feed_webhook(bot, dp, "sec", "bad", _update(5, "/start")))
    assert run(tg.feed_webhook(bot, dp, "sec", "sec", _update(5, "/start")))
    run(tg.feed_webhook(bot, dp, "sec", "sec", _update(5, "buy $BONK for me", update_id=2)))
    run(tg.feed_webhook(bot, dp, "sec", "sec", _update(5, "buy $BONK", "group", -100, update_id=3)))
    msgs = [m for m in sent if isinstance(m, SendMessage)]
    assert "Wizzy" in msgs[0].text and "<pre>" in msgs[0].text
    assert "runes don" in msgs[1].text
    assert len(msgs) == 2  # the group message did not mention the bot


def test_tg_quiz_flow_records_progress(tg_harness):
    ctx, bot, dp, sent = tg_harness
    lesson = apprentice.get("liquidity")

    def cb(data, n):
        return {
            "update_id": 100 + n,
            "callback_query": {
                "id": str(n),
                "from": {"id": 9, "is_bot": False, "first_name": "Q"},
                "chat_instance": "ci",
                "data": data,
                "message": {"message_id": 1, "date": 1700000000, "chat": {"id": 9, "type": "private"}, "text": "x"},
            },
        }

    run(tg.feed_webhook(bot, dp, "s", "s", cb("qs:liquidity", 0)))
    for i, q in enumerate(lesson.quiz):
        run(tg.feed_webhook(bot, dp, "s", "s", cb(f"qa:liquidity:{i}:{q.answer}", i + 1)))
    uid = ctx.wdb.user(tg_id="9")["id"]
    assert "lessons/liquidity" in apprentice.passed_slugs(ctx.wdb, uid)
    assert any(isinstance(m, AnswerCallbackQuery) for m in sent)
    assert "passed" in [m for m in sent if isinstance(m, SendMessage)][-1].text
