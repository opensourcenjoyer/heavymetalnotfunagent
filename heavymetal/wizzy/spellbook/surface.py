"""Spellbook on Telegram: /watch (confirmed with buttons), /watches, /unwatch. X requests get pointed to Telegram."""

from __future__ import annotations

import json

from heavymetal.wizzy.bots.core import Button, Reply
from heavymetal.wizzy.resolve import ResolveError, resolve_subject
from heavymetal.wizzy.spellbook import watches as W
from heavymetal.wizzy.spellbook.providers import PROVIDER

USAGE = (
    "Tell me what to watch, e.g.\n• warn me if $JUP top holders move\n• watch $WIF liquidity drops 30%\n"
    "• tell me if <wallet address> moves over 50 SOL\n• alert me if $X freeze authority changes"
)
TOKEN_KINDS = {"holders_moved", "liquidity_drop", "authority_change", "unlock"}


async def watch_reply(ctx, user_id: int, text: str, surface: str) -> Reply:
    if surface != "tg":
        return Reply("chitchat", text="Owls fly only on Telegram: DM Wizzy there to set a watch.")
    d = await W.parse_with_model(text, ctx.router_llm)
    if not d.kind or not d.target:
        return Reply("help", text=USAGE)
    if d.kind == "unlock" and not PROVIDER.available:
        return Reply("unavailable", text=PROVIDER.message)
    try:
        subject = await resolve_subject(ctx.env, d.target)
    except ResolveError as e:
        return Reply("error", text=f"The mists hide that target: {e}.")
    if d.kind in TOKEN_KINDS and subject.kind != "token":
        return Reply("error", text="That watch needs a token, and the address is a wallet.")
    if d.kind == "wallet_moves" and subject.kind != "wallet":
        return Reply("error", text="Wallet watches need a wallet address, and that one is a token.")
    ok, why = W.can_add(ctx, user_id)
    if not ok:
        return Reply("limited", text=why)
    ctx.wdb.subject(subject.kind, subject.key, subject.symbol)
    chat = ctx.wdb.one("SELECT tg_id FROM users WHERE id=?", (user_id,))["tg_id"]
    wid = W.create(ctx.wdb, user_id, d.kind, subject.key, d.params, chat, active=False)
    label = f"${subject.symbol}" if subject.symbol else f"{subject.key[:4]}…{subject.key[-4:]}"
    return Reply(
        "watch",
        "A new watch",
        f"Send an owl when {label}: {W.describe(d.kind, d.params)}?",
        buttons=[Button("🦉 Yes, watch it", data=f"wc:{wid}"), Button("✖ Cancel", data=f"wx:{wid}")],
    )


def list_text(ctx, user_id: int) -> str:
    rows = ctx.wdb.all("SELECT * FROM watches WHERE user_id=? AND active=1 ORDER BY id", (user_id,))
    if not rows:
        return "Your spellbook is empty. " + USAGE
    lines = []
    for r in rows:
        sym = ctx.wdb.one("SELECT symbol FROM subjects WHERE key=?", (r["target"],))
        label = f"${sym['symbol']}" if sym and sym["symbol"] else r["target"][:6] + "…"
        lines.append(f"#{r['id']} {label}: {W.describe(r['kind'], json.loads(r['params']))}")
    return f"Your watches ({len(rows)}/{W.slots(ctx, user_id)}):\n" + "\n".join(lines) + "\n/unwatch <id> to remove"


def confirm(ctx, user_id: int, wid: int) -> str:
    w = ctx.wdb.one("SELECT * FROM watches WHERE id=? AND user_id=?", (wid, user_id))
    if w is None:
        return "That watch is gone."
    if w["active"]:
        return "Already watching."
    ok, why = W.can_add(ctx, user_id)
    if not ok:
        return why
    ctx.wdb._x("UPDATE watches SET active=1 WHERE id=?", (wid,))
    return f"🦉 Watch #{wid} is set. An owl will come when it stirs."


def remove(ctx, user_id: int, wid: int) -> bool:
    return bool(ctx.wdb._x("DELETE FROM watches WHERE id=? AND user_id=?", (wid, user_id)).rowcount)


def tg_hook(router, ctx, helpers) -> None:
    from aiogram import F
    from aiogram.filters import Command, CommandObject
    from aiogram.types import CallbackQuery, Message

    uid_of, send, with_typing = helpers["uid_of"], helpers["send"], helpers["with_typing"]

    @router.message(Command("watch"))
    async def watch_cmd(m: Message, command: CommandObject) -> None:
        if not command.args:
            await m.answer(USAGE)
            return
        await send(m, await with_typing(m, watch_reply(ctx, uid_of(m), command.args, "tg")))

    @router.message(Command("watches"))
    async def watches_cmd(m: Message) -> None:
        await m.answer(list_text(ctx, uid_of(m)))

    @router.message(Command("unwatch"))
    async def unwatch_cmd(m: Message, command: CommandObject) -> None:
        try:
            wid = int((command.args or "").strip().lstrip("#"))
        except ValueError:
            await m.answer("Usage: /unwatch <id> (see /watches)")
            return
        await m.answer("Released." if remove(ctx, uid_of(m), wid) else "No such watch.")

    @router.callback_query(F.data.startswith("wc:"))
    async def confirm_cb(c: CallbackQuery) -> None:
        text = confirm(ctx, uid_of(c), int(c.data[3:]))
        await c.answer()
        if c.message:
            await c.message.answer(text)

    @router.callback_query(F.data.startswith("wx:"))
    async def cancel_cb(c: CallbackQuery) -> None:
        remove(ctx, uid_of(c), int(c.data[3:]))
        await c.answer("Cancelled")


def register() -> None:
    from heavymetal.wizzy import services
    from heavymetal.wizzy.bots import core, tg
    from heavymetal.wizzy.spellbook.poll import SpellbookWorker

    async def intent(ctx, user_id, it, surface):
        return await watch_reply(ctx, user_id, it.arg, surface)

    core.EXTRA_INTENTS["watch"] = intent
    tg.ROUTER_HOOKS.append(tg_hook)
    tg.EXTRA_HELP.append("\n/watch · set an owl alert · /watches · /unwatch &lt;id&gt;")
    services.WORKER_FACTORIES.append(lambda ctx, svc: SpellbookWorker(ctx, svc))
