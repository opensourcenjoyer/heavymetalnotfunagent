"""Surface-agnostic message handling: limits -> intent -> action -> Reply. Telegram and X render Replies."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from heavymetal.wizzy import apprentice, limits, reading
from heavymetal.wizzy.omen import OMEN_GLYPH, OMEN_LINE
from heavymetal.wizzy.resolve import ResolveError, resolve_subject
from heavymetal.wizzy.router import Intent, classify
from heavymetal.wizzy.writer import FOOTER

TRADE_LINE = "The runes don't trade. I read omens, I never buy, sell or send anything. Ask me to read a token instead."
CHITCHAT = [
    "The candles flicker. Send me a $TICKER, a contract address or a wallet and I'll read the bones.",
    "gm, wanderer. A ticker, a CA or a wallet, and the runes will speak.",
    "The cauldron hums. Try /learn for a lesson, or send a token to read.",
]
NOT_YET = "That spell is still being written. For now I can read tokens and wallets, scry omens and teach lessons."


@dataclass
class Button:
    label: str
    url: str | None = None
    data: str | None = None


@dataclass
class Reply:
    kind: str
    title: str = ""
    text: str = ""
    url: str | None = None
    buttons: list[Button] = field(default_factory=list)
    lesson: apprentice.Lesson | None = None
    omen: str | None = None
    quiz: tuple[str, int] | None = None  # (lesson slug, question index) to send next


# Feature handlers registered by later phases: intent kind -> async fn(ctx, user_id, intent, surface) -> Reply
EXTRA_INTENTS: dict[str, object] = {}


def lesson_reply(lesson: apprentice.Lesson) -> Reply:
    body = lesson.body
    if len(body) > 3200:
        body = body[:3200].rsplit("\n", 1)[0] + "\n…"
    buttons = [Button("🧪 Take the quiz", data=f"qs:{lesson.slug.removeprefix('lessons/')}")] if lesson.quiz else []
    return Reply("lesson", lesson.title, body, buttons=buttons, lesson=lesson)


def rank_reply(ctx, user_id: int) -> Reply:
    r = apprentice.rank(ctx.wdb, user_id)
    nxt = f" {r.needed} more lesson(s) to {r.next_name}." if r.next_name else " The highest circle."
    return Reply("rank", f"Rank: {r.name}", f"{r.passed}/{r.total} lessons passed.{nxt}")


async def scry(ctx, text: str) -> Reply:
    subject = await resolve_subject(ctx.env, text)
    if subject.kind != "token":
        return Reply("error", text="Scrying needs a token. For wallets, ask for a reading or tarot.")
    _, facts = await reading.get_facts(ctx, subject, light=True)
    t = facts.token
    kind = t.omen.kind if t.omen else "murky"
    sym = f"${t.symbol}" if t.symbol else subject.key[:6] + "…"
    lines = [f"{OMEN_GLYPH[kind]} {sym}: {OMEN_LINE[kind]}"]
    lines += [f"• {r}" for r in (t.omen.reasons if t.omen else [])[:3]]
    if facts.unknowns:
        lines.append(f"The mist hides: {', '.join(facts.unknowns[:3])}.")
    lines.append(FOOTER)
    lesson = apprentice.suggest_for(facts)
    return Reply("omen", f"Omen for {sym}", "\n".join(lines), lesson=lesson, omen=kind)


async def read_reply(ctx, user_id: int, text: str, surface: str, light: bool) -> Reply:
    r = await reading.read(ctx, text, surface=surface, user_id=user_id, light=light)
    lesson = apprentice.suggest_for(r.facts)
    buttons = [Button("📜 Full scroll", url=r.url)]
    if lesson:
        buttons.append(Button(f"📖 Lesson: {lesson.title}", data=f"ls:{lesson.slug.removeprefix('lessons/')}"))
    return Reply("reading", r.written.title, r.written.reading, url=r.url, buttons=buttons, lesson=lesson, omen=r.omen)


async def handle_text(
    ctx, user_id: int, text: str, *, surface: str, is_group: bool = False, chat_key: str | None = None
) -> Reply | None:
    """Route one message. Returns None when Wizzy should stay silent (flooded group chat)."""
    if not limits.check_chat(ctx, chat_key or f"u{user_id}").allowed:
        return None
    intent: Intent = await classify(text, ctx.router_llm if not is_group else None)
    return await act(ctx, user_id, intent, surface=surface, is_group=is_group)


async def act(ctx, user_id: int, intent: Intent, *, surface: str, is_group: bool = False) -> Reply:
    k = intent.kind
    if k == "trade_request":
        return Reply("trade", text=TRADE_LINE)
    if k == "spam":
        return Reply("chitchat", text=random.choice(CHITCHAT))
    if k == "chitchat":
        return Reply("chitchat", text=random.choice(CHITCHAT))
    if k == "lesson":
        hits = [h for h in _lesson_search(intent.arg)]
        lesson = hits[0] if hits else apprentice.next_lesson(ctx.wdb, user_id)
        return lesson_reply(lesson) if lesson else rank_reply(ctx, user_id)
    if k in EXTRA_INTENTS:
        return await EXTRA_INTENTS[k](ctx, user_id, intent, surface)
    if k in ("token", "wallet", "scry"):
        v = limits.check_reading(ctx, user_id, surface)
        if not v.allowed:
            mins = max(1, v.retry_after_s // 60)
            return Reply("limited", text=f"The candles need rest. Try again in about {mins} min. (/inner lifts limits)")
        try:
            if k == "scry":
                return await scry(ctx, intent.arg)
            return await read_reply(ctx, user_id, intent.arg, surface, light=is_group or surface == "x")
        except ResolveError as e:
            return Reply("error", text=f"The mists hide that: {e}.")
    return Reply("chitchat", text=NOT_YET)


def _lesson_search(query: str) -> list[apprentice.Lesson]:
    from heavymetal.kb.wiki import get_wiki

    out = []
    for h in get_wiki().search(query, limit=8):
        if h["slug"].startswith("lessons/") and h.get("origin") == "bundled":
            lesson = apprentice.get(h["slug"])
            if lesson:
                out.append(lesson)
    return out
