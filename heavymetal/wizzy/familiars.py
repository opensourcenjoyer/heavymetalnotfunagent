"""Familiars: off-chain badges for Inner Circle members. Each grants one perk flag that other features read."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Familiar:
    kind: str
    glyph: str
    name: str
    flag: str
    value: float
    perk: str


FAMILIARS = {
    "owl": Familiar("owl", "🦉", "Owl", "watch_slots", 5, "+5 spellbook watches"),
    "cat": Familiar("cat", "🐈‍⬛", "Cat", "early_prophecy", 1, "prophecies one hour before everyone else"),
    "raven": Familiar("raven", "🐦‍⬛", "Raven", "extra_readings_hour", 5, "+5 readings per hour"),
    "toad": Familiar("toad", "🐸", "Toad", "private_digest", 1, "a private weekly prophecy digest"),
}


def current(wdb, user_id: int) -> Familiar | None:
    row = wdb.one("SELECT kind FROM familiars WHERE user_id=?", (user_id,))
    return FAMILIARS.get(row["kind"]) if row else None


def choose(wdb, user_id: int, kind: str) -> Familiar | None:
    """Bind a familiar (Inner Circle only). Re-choosing swaps the perk."""
    fam = FAMILIARS.get(kind)
    if fam is None or wdb.tier(user_id) != "inner":
        return None
    wdb._x("DELETE FROM perks WHERE user_id=?", (user_id,))
    wdb._x("INSERT INTO perks(user_id, flag, value) VALUES(?,?,?)", (user_id, fam.flag, fam.value))
    wdb._x(
        "INSERT INTO familiars(user_id, kind, granted_at, source) VALUES(?,?,?, 'inner') "
        "ON CONFLICT(user_id) DO UPDATE SET kind=excluded.kind, granted_at=excluded.granted_at",
        (user_id, kind, time.time()),
    )
    return fam


def users_with_perk(wdb, flag: str) -> list[int]:
    rows = wdb.all("SELECT user_id FROM perks WHERE flag=?", (flag,))
    return [r["user_id"] for r in rows if wdb.tier(r["user_id"]) == "inner"]


def for_scroll(wdb, slug: str) -> Familiar | None:
    row = wdb.one(
        "SELECT f.kind FROM scrolls s JOIN requests r ON r.id=s.request_id JOIN familiars f ON f.user_id=r.user_id "
        "WHERE s.slug=?",
        (slug,),
    )
    return FAMILIARS.get(row["kind"]) if row else None


def picker_markup():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{f.glyph} {f.name}: {f.perk}", callback_data=f"fam:{k}")]
            for k, f in FAMILIARS.items()
        ]
    )


def tg_hook(router, ctx, helpers) -> None:
    from aiogram import F
    from aiogram.filters import Command
    from aiogram.types import CallbackQuery, Message

    uid_of = helpers["uid_of"]

    @router.message(Command("familiar"))
    async def familiar_cmd(m: Message) -> None:
        uid = uid_of(m)
        if ctx.wdb.tier(uid) != "inner":
            await m.answer("Familiars answer only to the Inner Circle. Send /inner to join.")
            return
        fam = current(ctx.wdb, uid)
        head = f"Your familiar: {fam.glyph} <b>{fam.name}</b> ({fam.perk}).\n\n" if fam else ""
        await m.answer(head + "Choose a familiar:", reply_markup=picker_markup())

    @router.callback_query(F.data.startswith("fam:"))
    async def familiar_pick(c: CallbackQuery) -> None:
        fam = choose(ctx.wdb, uid_of(c), c.data[4:])
        if fam is None:
            await c.answer("Only Inner Circle members can bind a familiar.", show_alert=True)
            return
        await c.answer(f"{fam.glyph} {fam.name} bound")
        if c.message:
            await c.message.answer(f"{fam.glyph} The <b>{fam.name}</b> is yours: {fam.perk}.")


def register() -> None:
    from heavymetal.wizzy.bots import tg

    tg.ROUTER_HOOKS.append(tg_hook)
    tg.EXTRA_HELP.append("\n/familiar · choose your familiar (Inner Circle)")
