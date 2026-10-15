"""Prophecy service: schedule, phrase, post (cat familiars first), resolve and publish the Sunday scoreboard."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import time
from dataclasses import asdict

from heavymetal.wizzy import familiars, jobs
from heavymetal.wizzy.facts import Facts, NarrativeFacts, Subject
from heavymetal.wizzy.prophecy import claims, narratives, resolve, scoreboard
from heavymetal.worker import BackgroundWorker

PROPHECY_INSTRUCTIONS = (
    "This is a PROPHECY post. FACTS.extra.prophecy.claim is a measurable claim decided in code. Rewrite it as one "
    "or two cryptic, playful sentences for a social post (under 220 characters), keeping its meaning, direction "
    "and numbers exactly. Never add buy/sell language or price targets. scrollTitle: a short title. "
    "scrollBodyMarkdown: '## Prophecy' with the claim stated plainly, then '## How it will be judged' with "
    "FACTS.extra.prophecy.judged."
)
JUDGED = {
    "narrative_share": "Against a fresh smallcap volume sweep 72 hours later.",
    "top5_hold": "Against the banked top-5 tickers three days later.",
    "fg_direction": "Against the banked Trench Fear & Greed index seven days later.",
    "volume_direction": "Against the banked smallcap volume seven days later.",
}


def prophecy_facts(c: claims.Claim) -> Facts:
    theme = c.subject.get("narrative") or c.subject.get("symbol") or c.kind
    return Facts(
        asOf=c.features.get("as_of") or time.time(),
        subject=Subject(kind="narrative"),
        narrative=NarrativeFacts(theme=str(theme)),
        extra={"prophecy": {"claim": c.claim, "kind": c.kind, "baseline": c.baseline, "judged": JUDGED[c.kind]}},
    )


def template(facts: Facts) -> tuple[str, str, str]:
    p = facts.extra["prophecy"]
    return f"🔮 {p['claim']}", "A prophecy", f"## Prophecy\n- {p['claim']}\n## How it will be judged\n- {p['judged']}"


async def gather_claims(ctx, now: float | None = None) -> list[claims.Claim]:
    from heavymetal.trenches.pulse import refresh, sweep

    pulse = await refresh(ctx.env)
    out = []
    try:
        _agg, pools = await sweep(ctx.env)
        shares = narratives.shares(ctx.wdb, narratives.kept(ctx.env, pools))
    except Exception:  # noqa: BLE001
        shares = {}
    for c in claims.candidates(pulse, shares, now):
        out.append(c)
    order = claims.next_kind(ctx.wdb)
    return sorted(out, key=lambda c: order.index(c.kind))


async def make_prophecy(ctx, now: float | None = None) -> int | None:
    from heavymetal.wizzy.reading import llm_allowed
    from heavymetal.wizzy.writer import FOOTER, write

    cands = await gather_claims(ctx, now)
    if not cands:
        return None
    c = cands[0]
    written = await write(
        ctx.writer if llm_allowed(ctx) else None,
        prophecy_facts(c),
        effort="low",
        instructions=PROPHECY_INSTRUCTIONS,
        template_fn=template,
    )
    text = written.reading.replace(FOOTER, "").strip()
    early = familiars.users_with_perk(ctx.wdb, "early_prophecy")
    public_at = time.time() + (3600 if early else 0)
    pid = claims.store(ctx.wdb, c, posted_text=text, public_at=public_at)
    for uid in early:
        row = ctx.wdb.one("SELECT tg_id FROM users WHERE id=?", (uid,))
        if row and row["tg_id"]:
            jobs.enqueue(
                ctx.wdb,
                "tg_dm",
                {"chat_id": row["tg_id"], "text": f"🐈‍⬛ An early whisper:\n{text}"},
                dedupe_key=f"early:{pid}:{uid}",
            )
    jobs.enqueue(ctx.wdb, "prophecy_post", {"id": pid}, dedupe_key=f"prophecy:{pid}", run_after=public_at)
    return pid


def slot_due(ctx, now: float | None = None) -> str | None:
    now = now or time.time()
    d = dt.datetime.fromtimestamp(now, dt.UTC)
    hours = list(ctx.wcfg.prophecy_hours_utc)[: max(0, ctx.wcfg.prophecies_per_day)]
    if d.hour not in hours:
        return None
    key = f"prophecy_slot:{d:%Y-%m-%d}:{d.hour}"
    return None if ctx.wdb.meta(key) else key


async def post_prophecy(ctx, svc, payload: dict) -> dict:
    row = ctx.wdb.one("SELECT * FROM prophecies WHERE id=?", (payload["id"],))
    if row is None or row["x_post_id"] or row["tg_msg_id"]:
        return {"skipped": True}
    text = f"{row['posted_text']}\nNFA · DYOR"
    out = {}
    if getattr(svc, "x", None) is not None:
        out["x"] = await svc.x.post(text[:280])
        ctx.wdb._x("UPDATE prophecies SET x_post_id=? WHERE id=?", (out["x"], row["id"]))
    if getattr(svc, "bot", None) is not None and ctx.wcfg.prophecy_channel:
        msg = await svc.bot.send_message(ctx.wcfg.prophecy_channel, text)
        out["tg"] = str(getattr(msg, "message_id", ""))
        ctx.wdb._x("UPDATE prophecies SET tg_msg_id=? WHERE id=?", (out["tg"], row["id"]))
    return out


async def post_scoreboard(ctx, svc, payload: dict) -> dict:
    row = ctx.wdb.one("SELECT * FROM scoreboards WHERE week=?", (payload["week"],))
    if row is None or row["x_post_id"]:
        return {"skipped": True}
    text = row["posted_text"]
    out = {}
    if getattr(svc, "x", None) is not None:
        out["x"] = await svc.x.post(text[:280])
        ctx.wdb._x("UPDATE scoreboards SET x_post_id=? WHERE week=?", (out["x"], payload["week"]))
    if getattr(svc, "bot", None) is not None and ctx.wcfg.prophecy_channel:
        await svc.bot.send_message(ctx.wcfg.prophecy_channel, text)
    for uid in familiars.users_with_perk(ctx.wdb, "private_digest"):
        u = ctx.wdb.one("SELECT tg_id FROM users WHERE id=?", (uid,))
        if u and u["tg_id"]:
            jobs.enqueue(
                ctx.wdb,
                "tg_dm",
                {"chat_id": u["tg_id"], "text": "🐸 Your private digest\n\n" + digest(ctx)},
                dedupe_key=f"digest:{payload['week']}:{uid}",
            )
    return out


def digest(ctx) -> str:
    _w, s, _t = scoreboard.build(ctx.wdb)
    lines = [f"Graded {s['n']}, voided {s['voids']}."]
    for k, v in s["by_kind"].items():
        lines.append(f"• {k}: {v['hit']} right, {v['miss']} wrong")
    open_rows = ctx.wdb.all("SELECT claim FROM prophecies WHERE status='open' ORDER BY ts DESC LIMIT 5")
    if open_rows:
        lines.append("Still unfolding:")
        lines += [f"• {r['claim']}" for r in open_rows]
    return "\n".join(lines)


async def send_dm(ctx, svc, payload: dict) -> dict:
    if getattr(svc, "bot", None) is None:
        raise RuntimeError("telegram bot not running")
    await svc.bot.send_message(int(payload["chat_id"]), payload["text"][:4000])
    return {"ok": True}


def scoreboard_due(ctx, now: float | None = None) -> str | None:
    now = now or time.time()
    d = dt.datetime.fromtimestamp(now, dt.UTC)
    if d.weekday() != 6 or d.hour < 18:
        return None
    week = scoreboard.week_key(now)
    return None if ctx.wdb.one("SELECT 1 FROM scoreboards WHERE week=?", (week,)) else week


class ProphecyWorker(BackgroundWorker):
    name = "wizzy-prophecy"

    def __init__(self, ctx, svc=None):
        super().__init__(ctx.env)
        self.ctx = ctx
        self.svc = svc

    def loops(self):
        return (self._pulse_loop, self._schedule_loop, self._resolve_loop, self._score_loop)

    async def _pulse_loop(self) -> None:
        from heavymetal.trenches.pulse import refresh

        while True:
            await refresh(self.ctx.env, force=True)  # banks trench_days and fg_days: the ground truth
            await asyncio.sleep(1200)

    async def _schedule_loop(self) -> None:
        while True:
            key = slot_due(self.ctx)
            if key:
                self.ctx.wdb.set_meta(key, str(time.time()))
                await make_prophecy(self.ctx)
            await asyncio.sleep(300)

    async def _resolve_loop(self) -> None:
        while True:
            await resolve.resolve_due(self.ctx)
            await asyncio.sleep(3600)

    async def _score_loop(self) -> None:
        while True:
            week = scoreboard_due(self.ctx)
            if week:
                w, s, text = scoreboard.build(self.ctx.wdb)
                if scoreboard.save(self.ctx.wdb, w, s, text):
                    jobs.enqueue(self.ctx.wdb, "scoreboard_post", {"week": w}, dedupe_key=f"score:{w}")
            await asyncio.sleep(1800)


# ---------------------------------------------------------------------- surfaces
async def narrative_reply(ctx, user_id, intent, surface):
    from heavymetal.trenches.pulse import sweep
    from heavymetal.wizzy.bots.core import Reply

    try:
        _agg, pools = await sweep(ctx.env)
    except Exception:  # noqa: BLE001
        return Reply("error", text="The trench sweep is misted right now. Try again soon.")
    shares = narratives.shares(ctx.wdb, narratives.kept(ctx.env, pools))
    top = sorted(
        ((n, v) for n, v in shares.items() if n != narratives.OTHER and v["share"]), key=lambda kv: -kv[1]["share"]
    )[:5]
    if not top:
        return Reply("narrative", text="No narrative stands out in the trench volume right now.")
    lines = [f"• {n}: {round(v['share'] * 100, 2)}% of smallcap volume across {v['pools']} pools" for n, v in top]
    return Reply("narrative", "Narratives in the trenches", "\n".join(lines) + "\n\nNFA · DYOR")


def recent_text(ctx) -> str:
    rows = ctx.wdb.all("SELECT * FROM prophecies ORDER BY ts DESC LIMIT 6")
    if not rows:
        return "No prophecies yet. The first arrives at the next scheduled hour."
    mark = {"hit": "✓", "miss": "✗", "n/a": "·", None: "…"}
    return "\n".join(f"{mark[r['outcome']]} {r['claim']}" for r in rows)


def register() -> None:
    from heavymetal.wizzy import services
    from heavymetal.wizzy.bots import core, tg

    services.WORKER_FACTORIES.append(lambda ctx, svc: ProphecyWorker(ctx, svc))
    services.JOB_HANDLERS.update({"prophecy_post": post_prophecy, "scoreboard_post": post_scoreboard, "tg_dm": send_dm})
    core.EXTRA_INTENTS["narrative"] = narrative_reply

    async def prophecies_cmd(ctx, message, args):
        return core.Reply("prophecies", "Recent prophecies", recent_text(ctx))

    async def scoreboard_cmd(ctx, message, args):
        _w, _s, text = scoreboard.build(ctx.wdb)
        return core.Reply("scoreboard", text=text)

    tg.EXTRA_COMMANDS["prophecies"] = prophecies_cmd
    tg.EXTRA_COMMANDS["scoreboard"] = scoreboard_cmd
    tg.EXTRA_HELP.append("\n/prophecies · recent prophecies · /scoreboard · how they fared")


def dump(c: claims.Claim) -> str:
    return json.dumps(asdict(c), default=str, indent=2)
