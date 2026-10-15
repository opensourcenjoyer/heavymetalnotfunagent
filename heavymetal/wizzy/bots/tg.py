"""Telegram surface (aiogram 3). DMs answer any message; groups answer commands and @mentions only.

Production uses a webhook (see web/app.py) verified by X-Telegram-Bot-Api-Secret-Token; local dev uses polling.
"""

from __future__ import annotations

import asyncio
import hmac
import html
from dataclasses import dataclass, field

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction, ChatType, ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update

from heavymetal import mascot
from heavymetal.wizzy import apprentice
from heavymetal.wizzy.bots.core import Reply, act, handle_text, lesson_reply, rank_reply
from heavymetal.wizzy.router import Intent

HELP = (
    "<b>Wizzy</b> reads Solana tokens and wallets. I never trade, never hold funds, never give financial advice.\n\n"
    "Send a <code>$TICKER</code>, a contract address, a DexScreener/pump.fun link or a wallet.\n\n"
    "/read &lt;token or wallet&gt; · full reading + scroll\n"
    "/scry &lt;CA&gt; · quick rug omen\n"
    "/learn · next lesson · /lesson &lt;topic&gt; · /rank\n"
    "/help"
)
EXTRA_COMMANDS: dict[str, object] = {}  # registered by later phases: name -> async fn(ctx, message, args) -> Reply
ROUTER_HOOKS: list[object] = []  # fn(router, ctx, helpers) attaching any handlers (payments, familiars, watches)
EXTRA_HELP: list[str] = []


def esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def mascot_block() -> str:
    return "<pre>" + esc("\n".join(mascot.POSES[(0, False)])) + "</pre>"


def keyboard(reply: Reply) -> InlineKeyboardMarkup | None:
    rows = []
    for b in reply.buttons:
        if b.url and b.url.startswith("https://"):
            rows.append([InlineKeyboardButton(text=b.label, url=b.url)])
        elif b.data:
            rows.append([InlineKeyboardButton(text=b.label, callback_data=b.data[:64])])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def render(reply: Reply) -> str:
    parts = []
    if reply.title:
        parts.append(f"<b>{esc(reply.title)}</b>")
    if reply.text:
        parts.append(esc(reply.text))
    if reply.url and not reply.url.startswith("https://"):
        parts.append(f"📜 Scroll: {esc(reply.url)}")  # localhost links can't be buttons
    return "\n\n".join(parts)[:4000]


# ---------------------------------------------------------------------- quizzes
@dataclass
class QuizSessions:
    """In-memory quiz progress: (user_id, slug) -> answers so far. Lost on restart, which only restarts a quiz."""

    answers: dict[tuple[int, str], list[bool]] = field(default_factory=dict)

    def start(self, uid: int, slug: str) -> None:
        self.answers[(uid, slug)] = []

    def answer(self, uid: int, slug: str, correct: bool) -> list[bool]:
        a = self.answers.setdefault((uid, slug), [])
        a.append(correct)
        return a

    def finish(self, uid: int, slug: str) -> None:
        self.answers.pop((uid, slug), None)


def question_markup(slug: str, qi: int, q: apprentice.Question) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=o[:60], callback_data=f"qa:{slug}:{qi}:{i}")] for i, o in enumerate(q.options)
        ]
    )


def question_text(lesson: apprentice.Lesson, qi: int) -> str:
    return f"🧪 <b>{esc(lesson.title)}</b> · question {qi + 1}/{len(lesson.quiz)}\n\n{esc(lesson.quiz[qi].text)}"


# ---------------------------------------------------------------------- dispatcher
def build_router(ctx) -> Router:
    r = Router(name="wizzy")
    quizzes = QuizSessions()

    def uid_of(m: Message | CallbackQuery) -> int:
        return ctx.wdb.user(tg_id=str(m.from_user.id))["id"]

    async def send(m: Message, reply: Reply | None) -> None:
        if reply is None:
            return
        await m.answer(render(reply), reply_markup=keyboard(reply), disable_web_page_preview=True)

    async def with_typing(m: Message, coro):
        task = asyncio.create_task(coro)
        while not task.done():
            try:
                await m.bot.send_chat_action(m.chat.id, ChatAction.TYPING)
            except Exception:  # noqa: BLE001
                pass
            await asyncio.wait({task}, timeout=4.5)
        return task.result()

    @r.message(CommandStart())
    async def start(m: Message) -> None:
        await m.answer(mascot_block() + "\n" + HELP + "".join(EXTRA_HELP), disable_web_page_preview=True)

    @r.message(Command("help"))
    async def help_(m: Message) -> None:
        await m.answer(HELP + "".join(EXTRA_HELP), disable_web_page_preview=True)

    @r.message(Command("read"))
    async def read_cmd(m: Message, command: CommandObject) -> None:
        if not command.args:
            await m.answer("Usage: /read $TICKER, a contract address or a wallet")
            return
        is_group = m.chat.type != ChatType.PRIVATE
        reply = await with_typing(
            m, act(ctx, uid_of(m), Intent("token", command.args), surface="tg", is_group=is_group)
        )
        await send(m, reply)

    @r.message(Command("scry"))
    async def scry_cmd(m: Message, command: CommandObject) -> None:
        if not command.args:
            await m.answer("Usage: /scry &lt;contract address or $TICKER&gt;")
            return
        await send(m, await with_typing(m, act(ctx, uid_of(m), Intent("scry", command.args), surface="tg")))

    @r.message(Command("learn"))
    async def learn_cmd(m: Message) -> None:
        uid = uid_of(m)
        lesson = apprentice.next_lesson(ctx.wdb, uid)
        if lesson is None:
            await send(m, rank_reply(ctx, uid))
            return
        apprentice.start(ctx.wdb, uid, lesson.slug)
        await send(m, lesson_reply(lesson))

    @r.message(Command("lesson"))
    async def lesson_cmd(m: Message, command: CommandObject) -> None:
        uid = uid_of(m)
        if not command.args:
            names = " · ".join(x.slug.removeprefix("lessons/") for x in apprentice.lessons())
            await m.answer(f"Lessons: {esc(names)}\nUsage: /lesson liquidity")
            return
        lesson = apprentice.get(command.args.strip().lower()) or None
        reply = lesson_reply(lesson) if lesson else await act(ctx, uid, Intent("lesson", command.args), surface="tg")
        if lesson:
            apprentice.start(ctx.wdb, uid, lesson.slug)
        await send(m, reply)

    @r.message(Command("rank"))
    async def rank_cmd(m: Message) -> None:
        await send(m, rank_reply(ctx, uid_of(m)))

    @r.callback_query(F.data.startswith("ls:"))
    async def lesson_button(c: CallbackQuery) -> None:
        lesson = apprentice.get(c.data[3:])
        await c.answer()
        if lesson and c.message:
            apprentice.start(ctx.wdb, uid_of(c), lesson.slug)
            reply = lesson_reply(lesson)
            await c.message.answer(render(reply), reply_markup=keyboard(reply), disable_web_page_preview=True)

    @r.callback_query(F.data.startswith("qs:"))
    async def quiz_start(c: CallbackQuery) -> None:
        slug = c.data[3:]
        lesson = apprentice.get(slug)
        await c.answer()
        if not lesson or not lesson.quiz or not c.message:
            return
        quizzes.start(uid_of(c), slug)
        await c.message.answer(question_text(lesson, 0), reply_markup=question_markup(slug, 0, lesson.quiz[0]))

    @r.callback_query(F.data.startswith("qa:"))
    async def quiz_answer(c: CallbackQuery) -> None:
        try:
            _, slug, qi_s, choice_s = c.data.split(":")
            qi, choice = int(qi_s), int(choice_s)
        except ValueError:
            await c.answer()
            return
        lesson = apprentice.get(slug)
        if not lesson or qi >= len(lesson.quiz) or not c.message:
            await c.answer()
            return
        uid = uid_of(c)
        q = lesson.quiz[qi]
        correct = choice == q.answer
        answers = quizzes.answer(uid, slug, correct)
        await c.answer("✨ Correct" if correct else f"🌫 Not quite: {q.options[q.answer][:150]}", show_alert=not correct)
        if qi + 1 < len(lesson.quiz):
            await c.message.answer(
                question_text(lesson, qi + 1), reply_markup=question_markup(slug, qi + 1, lesson.quiz[qi + 1])
            )
            return
        score = sum(answers[-len(lesson.quiz) :])
        quizzes.finish(uid, slug)
        passed = apprentice.record_quiz(ctx.wdb, uid, lesson.slug, score, len(lesson.quiz))
        rank = apprentice.rank(ctx.wdb, uid)
        verdict = "passed ✨" if passed else "not yet passed (try again with the button above)"
        await c.message.answer(
            f"{score}/{len(lesson.quiz)}: lesson {verdict}\nRank: <b>{esc(rank.name)}</b> "
            f"({rank.passed}/{rank.total} lessons). /learn for the next one."
        )

    helpers = {"uid_of": uid_of, "send": send, "with_typing": with_typing, "render": render, "keyboard": keyboard}
    for hook in ROUTER_HOOKS:
        hook(r, ctx, helpers)

    for name, fn in EXTRA_COMMANDS.items():

        def _make(fn=fn):
            async def handler(m: Message, command: CommandObject) -> None:
                await send(m, await with_typing(m, fn(ctx, m, command.args or "")))

            return handler

        r.message(Command(name))(_make())

    @r.message(F.text)
    async def any_text(m: Message) -> None:
        text = m.text or ""
        is_group = m.chat.type != ChatType.PRIVATE
        if is_group:
            me = await m.bot.me()
            mention = f"@{me.username}".lower() if me.username else None
            if not mention or mention not in text.lower():
                return
            text = text.replace(f"@{me.username}", "").strip()
        reply = await with_typing(
            m, handle_text(ctx, uid_of(m), text, surface="tg", is_group=is_group, chat_key=f"c{m.chat.id}")
        )
        await send(m, reply)

    return r


def build(ctx, token: str | None = None) -> tuple[Bot, Dispatcher]:
    from heavymetal.wizzy.features import register_all

    register_all()
    token = token or ctx.cfg.keys.telegram_bot_token
    if not token:
        raise RuntimeError("set the Telegram bot token: /keys set telegram_bot_token or TELEGRAM_BOT_TOKEN")
    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(build_router(ctx))
    return bot, dp


def verify_secret(expected: str, header: str | None) -> bool:
    return bool(expected) and hmac.compare_digest(expected.encode(), (header or "").encode())


async def feed_webhook(bot: Bot, dp: Dispatcher, expected_secret: str, header: str | None, body: dict) -> bool:
    """Process one webhook update after checking Telegram's secret header. Returns False if rejected."""
    if not verify_secret(expected_secret, header):
        return False
    update = Update.model_validate(body, context={"bot": bot})
    await dp.feed_update(bot, update)
    return True


async def run_polling(ctx) -> None:
    bot, dp = build(ctx)
    await bot.delete_webhook(drop_pending_updates=False)
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query", "pre_checkout_query"])
    finally:
        await bot.session.close()
