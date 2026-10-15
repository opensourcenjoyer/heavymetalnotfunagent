import asyncio
import datetime as dt
import json
import time

from heavymetal.wizzy import familiars, jobs
from heavymetal.wizzy.prophecy import claims, narratives, resolve, scoreboard, service
from tests.wizzy_fakes import make_ctx


def run(c):
    return asyncio.run(c)


def pool(sym, name, v24, v6, mint=None):
    return {"symbol": sym, "name": name, "mint": mint or f"M{sym}", "volume": {"h24": v24, "h6": v6}}


def test_tagging():
    assert narratives.tag("WIF", "dogwifhat") == "dogs"
    assert narratives.tag("GOAT", "Goatseus AI agent") == "AI agents"
    assert narratives.tag("XYZ", "nothing here") == narratives.OTHER


def test_shares_and_narrative_claim(tmp_path):
    ctx = make_ctx(tmp_path)
    pools = [
        pool("WIF", "dog wif hat", 600, 200),
        pool("PUP", "puppy", 300, 100),
        pool("INU", "inu", 100, 40),
        pool("ZZZ", "plain", 1000, 100),
    ]
    sh = narratives.shares(ctx.wdb, pools)
    assert sh["dogs"]["share"] == 0.5 and sh["dogs"]["pools"] == 3
    c = claims.narrative_claim(sh, overall_pace=0.5, now=1000.0)
    assert c.kind == "narrative_share" and c.op == ">=" and c.threshold == 0.5  # dogs pace 1.36 > 0.5
    assert "50.0% now" in c.claim and c.features["as_of"] == 1000.0
    c2 = claims.narrative_claim(sh, overall_pace=5.0, now=1000.0)
    assert c2.op == "<" and "shrinks" in c2.claim


def pulse_fixture():
    return {
        "today": {"smallcap_vol": 2_000_000.0, "pace": 1.0, "top5": [{"symbol": "RSGP", "share": 0.31}]},
        "fear_greed": {"index": 62, "arms": {"momentum": 70}, "band": "greed"},
        "ema7": 2.1e6,
        "ema14": 1.9e6,
    }


def test_candidates_all_kinds_and_rotation(tmp_path):
    ctx = make_ctx(tmp_path)
    cs = claims.candidates(pulse_fixture(), {}, now=1000.0)
    assert {c.kind for c in cs} == {"top5_hold", "fg_direction", "volume_direction"}
    fg = next(c for c in cs if c.kind == "fg_direction")
    assert fg.op == ">" and fg.threshold == 62 and fg.subject["resolve_day"] == claims.day_str(1000.0, 7)
    claims.store(ctx.wdb, cs[0])
    assert claims.next_kind(ctx.wdb)[-1] == cs[0].kind


def _store_backdated(ctx, c, hours_ago):
    pid = claims.store(ctx.wdb, c)
    ctx.wdb._x("UPDATE prophecies SET ts=? WHERE id=?", (time.time() - hours_ago * 3600, pid))
    return pid


def _bank(ctx, table, day, **cols):
    keys = ", ".join(["day", *cols, "updated_at"])
    marks = ", ".join("?" * (len(cols) + 2))
    ctx.env.db.conn.execute(
        f"INSERT OR REPLACE INTO {table}({keys}) VALUES({marks})", (day, *cols.values(), time.time())
    )
    ctx.env.db.conn.commit()


def test_resolution_matured_only_and_void_without_data(tmp_path):
    ctx = make_ctx(tmp_path)
    young = claims.top5_claim([{"symbol": "AAA", "share": 0.2}], now=time.time())
    _store_backdated(ctx, young, 10)  # 72h horizon: not matured
    old = claims.top5_claim([{"symbol": "BBB", "share": 0.2}], now=time.time() - 80 * 3600)
    pid_old = _store_backdated(ctx, old, 80)
    vol = claims.volume_claim(1e6, 2e6, 1e6, now=time.time() - 200 * 3600)  # claims "higher"
    pid_vol = _store_backdated(ctx, vol, 200)
    assert {r["id"] for r in resolve.due(ctx.wdb)} == {pid_old, pid_vol}
    _bank(ctx, "trench_days", vol.subject["resolve_day"], smallcap_vol=1.5e6)
    out = run(resolve.resolve_due(ctx))
    assert out == {"hit": 1, "miss": 0, "n/a": 1}  # volume hit; top5 voided (no banked day)
    rows = {r["id"]: r for r in ctx.wdb.all("SELECT * FROM prophecies")}
    assert rows[pid_old]["status"] == "void" and rows[pid_vol]["outcome"] == "hit"
    assert rows[pid_vol]["value_at_resolve"] == 1.5e6


def test_top5_and_narrative_resolution(tmp_path):
    ctx = make_ctx(tmp_path)
    t = claims.top5_claim([{"symbol": "AAA", "share": 0.2}], now=time.time() - 80 * 3600)
    pid = _store_backdated(ctx, t, 80)
    _bank(ctx, "trench_days", t.subject["resolve_day"], top=json.dumps([{"symbol": "ZZ"}, {"symbol": "AAA"}]))
    n = claims.narrative_claim(
        {"dogs": {"share": 0.4, "pace": 2.0, "pools": 5, "vol24": 1, "vol6": 1}}, 1.0, now=time.time() - 80 * 3600
    )
    pid_n = _store_backdated(ctx, n, 80)
    cache = {"shares": {"dogs": {"share": 0.3}}}
    for row in resolve.due(ctx.wdb):
        run(resolve.resolve_one(ctx, row, cache))
    rows = {r["id"]: r for r in ctx.wdb.all("SELECT * FROM prophecies")}
    assert rows[pid]["outcome"] == "hit" and rows[pid]["value_at_resolve"] == 2.0
    assert rows[pid_n]["outcome"] == "miss" and rows[pid_n]["value_at_resolve"] == 0.3


def test_stale_banked_row_does_not_count(tmp_path):
    ctx = make_ctx(tmp_path)
    fg = claims.fg_claim({"index": 50, "arms": {"momentum": 80}}, now=time.time() - 200 * 3600)
    _store_backdated(ctx, fg, 200)
    ctx.env.db.conn.execute(
        "INSERT INTO fg_days(day, idx, updated_at) VALUES(?,?,?)",
        (fg.subject["resolve_day"], 70, time.time() - 300 * 3600),
    )  # stamped before the claim
    ctx.env.db.conn.commit()
    assert run(resolve.resolve_due(ctx)) == {"hit": 0, "miss": 0, "n/a": 1}


def test_scoreboard_text_names_wrong_calls_and_flags_thin(tmp_path):
    ctx = make_ctx(tmp_path)
    now = time.time()
    for outcome, val in (("hit", 2.0), ("miss", 0.031), ("n/a", None)):
        c = claims.narrative_claim({"cats": {"share": 0.1, "pace": 2, "pools": 4, "vol24": 1, "vol6": 1}}, 1, now)
        pid = claims.store(ctx.wdb, c)
        ctx.wdb._x(
            "UPDATE prophecies SET status='resolved', outcome=?, value_at_resolve=?, resolved_ts=? WHERE id=?",
            (outcome, val, now - 3600, pid),
        )
    week, s, text = scoreboard.build(ctx.wdb, now)
    assert s["n"] == 2 and s["hits"] == 1 and s["voids"] == 1 and s["thin"] is True and s["hit_rate"] == 0.5
    assert "✗ Wrong:" in text and "3.1%" in text and "thin sample" in text
    assert scoreboard.save(ctx.wdb, week, s, text) and not scoreboard.save(ctx.wdb, week, s, text)


def test_slots_and_scoreboard_schedule(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.wcfg.prophecy_hours_utc = [9, 15, 21]
    ctx.wcfg.prophecies_per_day = 2
    at = lambda d, h: dt.datetime(2026, 10, d, h, 5, tzinfo=dt.UTC).timestamp()  # noqa: E731
    assert service.slot_due(ctx, at(16, 9)) and service.slot_due(ctx, at(16, 15))
    assert service.slot_due(ctx, at(16, 21)) is None  # only 2 per day
    ctx.wdb.set_meta(service.slot_due(ctx, at(16, 9)), "1")
    assert service.slot_due(ctx, at(16, 9)) is None
    assert service.scoreboard_due(ctx, at(18, 19))  # 2026-10-18 is a Sunday
    assert service.scoreboard_due(ctx, at(18, 10)) is None and service.scoreboard_due(ctx, at(17, 19)) is None


def test_make_prophecy_whispers_to_cats_first(tmp_path, monkeypatch):
    ctx = make_ctx(tmp_path)
    uid = ctx.wdb.user(tg_id="555")["id"]
    ctx.wdb._x("UPDATE users SET tier='inner', tier_expires_at=? WHERE id=?", (time.time() + 999, uid))
    familiars.choose(ctx.wdb, uid, "cat")

    async def fake_gather(ctx_, now=None):
        return claims.candidates(pulse_fixture(), {}, now=time.time())

    monkeypatch.setattr(service, "gather_claims", fake_gather)
    pid = run(service.make_prophecy(ctx))
    row = ctx.wdb.one("SELECT * FROM prophecies WHERE id=?", (pid,))
    assert row["posted_text"].startswith("🔮") and row["public_at"] > time.time() + 3000
    kinds = {r["kind"]: r for r in ctx.wdb.all("SELECT * FROM jobs")}
    assert json.loads(kinds["tg_dm"]["payload"])["chat_id"] == "555"
    assert kinds["prophecy_post"]["run_after"] >= row["public_at"] - 1

    class Svc:
        x = None
        sent = []

        class bot:
            @staticmethod
            async def send_message(chat, text):
                Svc.sent.append((chat, text))
                return type("M", (), {"message_id": 7})()

    ctx.wcfg.prophecy_channel = "@wizzy_prophecies"
    out = run(service.post_prophecy(ctx, Svc, {"id": pid}))
    assert out["tg"] == "7" and Svc.sent[0][0] == "@wizzy_prophecies" and "NFA" in Svc.sent[0][1]
    assert run(service.post_prophecy(ctx, Svc, {"id": pid})) == {"skipped": True}
    assert jobs.claim(ctx.wdb)  # queue usable after posting
