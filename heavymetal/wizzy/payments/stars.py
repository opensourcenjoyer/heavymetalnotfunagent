"""Inner Circle in Telegram: a Telegram Stars subscription (Telegram requires Stars for digital goods in bots)."""

from __future__ import annotations

import datetime as dt

from heavymetal.wizzy.payments import entitlements as ent

SUBSCRIPTION_PERIOD_S = 2592000  # 30 days, the only period Telegram allows


def inner_status_text(ctx, uid: int) -> str:
    from heavymetal.wizzy import familiars

    row = ctx.wdb.one("SELECT tier_expires_at FROM users WHERE id=?", (uid,))
    until = dt.datetime.fromtimestamp(row["tier_expires_at"], dt.UTC).strftime("%Y-%m-%d") if row else "?"
    fam = familiars.current(ctx.wdb, uid)
    famline = f"\nFamiliar: {fam.glyph} {fam.name} ({fam.perk})" if fam else "\nNo familiar yet: /familiar"
    return f"✨ You are in the Inner Circle until {until}.{famline}"


def tg_hook(router, ctx, helpers) -> None:
    from aiogram import F
    from aiogram.filters import Command
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message, PreCheckoutQuery

    uid_of = helpers["uid_of"]
    w = ctx.wcfg

    @router.message(Command("inner"))
    async def inner_cmd(m: Message) -> None:
        uid = uid_of(m)
        rows = []
        base = w.base_url.rstrip("/")
        if ctx.wdb.tier(uid) == "inner":
            text = inner_status_text(ctx, uid)
            if base.startswith("https://"):
                rows.append(
                    [
                        InlineKeyboardButton(
                            text="📜 Read scrolls on the web",
                            url=f"{base}/inner/login?k={ent.inner_token(ctx.wdb, uid, w.inner_days)}",
                        )
                    ]
                )
        else:
            text = (
                f"<b>The Inner Circle</b>\n{w.inner_days} days: every full scroll free, "
                f"{w.inner_readings_per_hour} readings per hour, {w.inner_watches} spellbook watches and a familiar."
            )
            link = await m.bot.create_invoice_link(
                title="Wizzy Inner Circle",
                description=f"{w.inner_days} days of full scrolls, more readings and watches, and a familiar.",
                payload=f"inner:{uid}",
                currency="XTR",
                prices=[LabeledPrice(label="Inner Circle (30 days)", amount=w.inner_price_stars)],
                subscription_period=SUBSCRIPTION_PERIOD_S,
            )
            rows.append([InlineKeyboardButton(text=f"⭐ Join for {w.inner_price_stars} Stars / 30 days", url=link)])
            if w.pay_to and base.startswith("https://"):
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=f"💠 Pay {w.inner_price_usdc:g} USDC on the web",
                            url=f"{base}/inner/pay?u={ent.user_token(ctx.wdb, uid)}",
                        )
                    ]
                )
        await m.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None)

    @router.pre_checkout_query()
    async def pre_checkout(q: PreCheckoutQuery) -> None:
        uid = ctx.wdb.user(tg_id=str(q.from_user.id))["id"]
        ok = q.invoice_payload == f"inner:{uid}" and q.currency == "XTR" and q.total_amount == w.inner_price_stars
        await q.answer(ok=ok, error_message=None if ok else "This invoice is not valid any more. Send /inner again.")

    @router.message(F.successful_payment)
    async def paid(m: Message) -> None:
        sp = m.successful_payment
        uid = uid_of(m)
        if sp.invoice_payload != f"inner:{uid}":
            return
        until = float(sp.subscription_expiration_date) if sp.subscription_expiration_date else None
        granted = ent.grant_inner(
            ctx.wdb,
            uid,
            days=w.inner_days,
            method="stars",
            tx_key=f"stars:{sp.telegram_payment_charge_id}",
            amount=sp.total_amount,
            until=until,
        )
        if not granted:
            return
        from heavymetal.wizzy import familiars

        await m.answer(
            inner_status_text(ctx, uid) + "\n\nChoose your familiar:", reply_markup=familiars.picker_markup()
        )
