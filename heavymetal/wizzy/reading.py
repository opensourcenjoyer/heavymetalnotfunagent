"""The reading pipeline: resolve -> facts (cached) -> writer -> scroll. Shared by the CLI, Telegram and X."""

from __future__ import annotations

import time
from dataclasses import dataclass

from heavymetal.wizzy import scrolls
from heavymetal.wizzy.build import build_facts
from heavymetal.wizzy.charts import price_chart_url
from heavymetal.wizzy.facts import Facts
from heavymetal.wizzy.resolve import ResolveError, Subject, resolve_subject
from heavymetal.wizzy.writer import Written, write


@dataclass
class Reading:
    subject: Subject
    facts: Facts
    written: Written
    slug: str
    url: str
    cached: bool = False

    @property
    def omen(self) -> str | None:
        t = self.facts.token
        return t.omen.kind if t and t.omen else None


def cached_facts(ctx, subject_id: int) -> Facts | None:
    r = ctx.wdb.one(
        "SELECT facts FROM facts_snapshots WHERE subject_id=? AND expires_at>? ORDER BY as_of DESC LIMIT 1",
        (subject_id, time.time()),
    )
    return Facts.model_validate_json(r["facts"]) if r else None


def store_facts(ctx, subject_id: int, facts: Facts) -> None:
    ctx.wdb._x(
        "INSERT INTO facts_snapshots(subject_id, facts, as_of, expires_at) VALUES(?,?,?,?)",
        (subject_id, facts.model_dump_json(), facts.asOf, facts.asOf + ctx.wcfg.facts_ttl_s),
    )


def llm_allowed(ctx) -> bool:
    """Writer only while under the daily budget; otherwise readings are templated."""
    if ctx.writer is None:
        return False
    return ctx.wdb.spend_since(time.time() - 86400) < ctx.wcfg.daily_llm_budget_usd


async def get_facts(ctx, subject: Subject, light: bool = False) -> tuple[int, Facts]:
    sid = ctx.wdb.subject(subject.kind, subject.key, subject.symbol)
    facts = cached_facts(ctx, sid)
    if facts is None:
        facts = await build_facts(ctx.env, subject, light=light)
        store_facts(ctx, sid, facts)
    return sid, facts


async def read(
    ctx, text: str, *, surface: str = "cli", user_id: int | None = None, light: bool = False, reuse: bool = True
) -> Reading:
    """Full reading for whatever the user typed. Raises ResolveError when nothing resolves."""
    t0 = time.time()
    rid = ctx.wdb.add_request(user_id, surface, text, "reading")
    try:
        async with ctx.readings_sem:
            subject = await resolve_subject(ctx.env, text)
            sid, facts = await get_facts(ctx, subject, light=light)
            if reuse:
                prev = scrolls.recent_for_subject(ctx.wdb, sid, subject.kind, ctx.wcfg.dedupe_ca_minutes * 60)
                if prev is not None:
                    ctx.wdb.finish_request(rid, "reused", sid, 0.0, int((time.time() - t0) * 1000))
                    w = Written(prev.reading, prev.title, prev.body_md, templated=False)
                    return Reading(subject, facts, w, prev.slug, scrolls.public_url(ctx.wcfg.base_url, prev.slug), True)
            written = await write(ctx.writer if llm_allowed(ctx) else None, facts, effort=ctx.wcfg.writer_effort)
            omen = facts.token.omen.kind if facts.token and facts.token.omen else None
            chart = price_chart_url(facts, omen, ctx.cfg.keys.quickchart_api_key)
            slug = scrolls.save(
                ctx.wdb,
                label=subject.symbol or subject.kind,
                kind=subject.kind,
                title=written.title,
                reading=written.reading,
                body_md=written.body,
                omen=omen,
                subject_id=sid,
                request_id=rid,
                price_usdc=ctx.wcfg.scroll_price_usdc,
                chart_urls=[chart] if chart else [],
            )
    except ResolveError:
        ctx.wdb.finish_request(rid, "unresolved", None, 0.0, int((time.time() - t0) * 1000))
        raise
    except Exception:
        ctx.wdb.finish_request(rid, "error", None, 0.0, int((time.time() - t0) * 1000))
        raise
    ctx.wdb.finish_request(
        rid, "templated" if written.templated else "ok", sid, written.cost_usd, int((time.time() - t0) * 1000)
    )
    return Reading(subject, facts, written, slug, scrolls.public_url(ctx.wcfg.base_url, slug))
