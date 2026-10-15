"""`wizzy` command: the public, read-only wizard bot."""

from __future__ import annotations

import argparse
import asyncio
import sys


def _migrate(_a) -> int:
    from heavymetal.wizzy.db import WizzyDB

    db = WizzyDB()
    print(f"wizzy.db ready at {db.path} (schema v{db.meta('schema_version')})")
    return 0


async def _read(a) -> int:
    from heavymetal.wizzy import cli
    from heavymetal.wizzy.ctx import open_ctx
    from heavymetal.wizzy.reading import read
    from heavymetal.wizzy.resolve import ResolveError

    ctx = open_ctx()
    try:
        with cli.waiting():
            r = await read(ctx, " ".join(a.input), surface="cli", light=a.quick, reuse=not a.fresh)
        cli.show_reading(r)
        return 0
    except ResolveError as e:
        cli.console.print(f"[yellow]The mists hide that: {e}[/yellow]")
        return 1
    finally:
        await ctx.aclose()


async def _tg(a) -> int:
    from heavymetal.wizzy.bots import tg
    from heavymetal.wizzy.ctx import open_ctx

    ctx = open_ctx()
    try:
        if a.set_webhook:
            from heavymetal.wizzy.services import set_webhook

            print(f"webhook set: {await set_webhook(ctx)}")
            return 0
        if not a.polling:
            print("Telegram webhooks are served by `wizzy serve`; use `wizzy tg --polling` for local testing.")
            return 2
        print("Wizzy is listening on Telegram (polling). Ctrl+C to stop.")
        await tg.run_polling(ctx)
        return 0
    finally:
        await ctx.aclose()


async def _serve(_a) -> int:
    from heavymetal.wizzy.ctx import open_ctx
    from heavymetal.wizzy.services import serve

    ctx = open_ctx()
    try:
        await serve(ctx)
        return 0
    finally:
        await ctx.aclose()


async def _tarot(a) -> int:
    from heavymetal.wizzy import cli
    from heavymetal.wizzy.ctx import open_ctx
    from heavymetal.wizzy.resolve import ResolveError
    from heavymetal.wizzy.tarot import tarot_read

    ctx = open_ctx()
    try:
        with cli.waiting("drawing the cards"):
            scroll, url, cached = await tarot_read(ctx, a.wallet, user_id=None, surface="cli")
        cli.show_scroll(scroll, url, cached)
        return 0
    except ResolveError as e:
        cli.console.print(f"[yellow]The mists hide that: {e}[/yellow]")
        return 1
    finally:
        await ctx.aclose()


async def _prophecy(a) -> int:
    from heavymetal.wizzy.ctx import open_ctx
    from heavymetal.wizzy.prophecy import service

    ctx = open_ctx()
    try:
        if a.dry_run:
            for c in await service.gather_claims(ctx):
                print(service.dump(c))
            return 0
        pid = await service.make_prophecy(ctx)
        print(f"prophecy #{pid} stored and queued for posting" if pid else "no claim could be made right now")
        return 0
    finally:
        await ctx.aclose()


async def _score(a) -> int:
    from heavymetal.wizzy.ctx import open_ctx
    from heavymetal.wizzy.prophecy import resolve, scoreboard

    ctx = open_ctx()
    try:
        if not a.dry_run:
            print(f"resolved: {await resolve.resolve_due(ctx)}")
        _w, _s, text = scoreboard.build(ctx.wdb)
        print(text)
        return 0
    finally:
        await ctx.aclose()


COUNTS = {
    "scrolls": "SELECT COUNT(*) AS n FROM scrolls",
    "users": "SELECT COUNT(*) AS n FROM users",
    "inner": "SELECT COUNT(*) AS n FROM users WHERE tier='inner'",
    "watches": "SELECT COUNT(*) AS n FROM watches WHERE active=1",
    "open prophecies": "SELECT COUNT(*) AS n FROM prophecies WHERE status='open'",
    "queued jobs": "SELECT COUNT(*) AS n FROM jobs WHERE status='queued'",
}


def _status(_a) -> int:
    import json

    from heavymetal.data.connectors import status
    from heavymetal.wizzy.ctx import open_ctx
    from heavymetal.wizzy.services import spend_report

    ctx = open_ctx()
    try:
        w = ctx.wcfg
        print(f"enabled={w.enabled} tg={w.tg_enabled} x={w.x_enabled} base_url={w.base_url}")
        key = "set" if ctx.writer else "missing (templated readings)"
        print(f"writer={w.writer_model} ({w.writer_effort}) router={w.router_model} model key={key}")
        print("spend:", json.dumps(spend_report(ctx)))
        print(" ".join(f"{name}={ctx.wdb.one(sql)['n']}" for name, sql in COUNTS.items()))
        for c in status(ctx.cfg, "wizzy"):
            print(f"  {'✓' if c['configured'] else '·'} {c['name']}: {c['unlocks']}")
        return 0
    finally:
        asyncio.run(ctx.aclose())


def run(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="wizzy", description="Wizzy: read-only Solana wizard for Telegram, X and the web")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="create or upgrade wizzy.db")
    rp = sub.add_parser("read", help="read a ticker, mint, link or wallet in the terminal")
    rp.add_argument("input", nargs="+")
    rp.add_argument("--quick", action="store_true", help="light audit (no holder scan, no protocol lookup)")
    rp.add_argument("--fresh", action="store_true", help="ignore a recent scroll for the same subject")
    tp = sub.add_parser("tg", help="run the Telegram bot")
    tp.add_argument("--polling", action="store_true", help="long-polling (local dev)")
    tp.add_argument("--set-webhook", action="store_true", help="register <base_url>/tg/webhook with Telegram")
    tap = sub.add_parser("tarot", help="three tarot cards for a wallet")
    tap.add_argument("wallet")
    pp = sub.add_parser("prophecy", help="make one prophecy now (--dry-run: print candidate claims only)")
    pp.add_argument("--dry-run", action="store_true")
    sp = sub.add_parser("score", help="resolve matured prophecies and print the scoreboard")
    sp.add_argument("--dry-run", action="store_true", help="print the scoreboard without resolving")
    sub.add_parser("status", help="settings, spend, counts and keys")
    sub.add_parser("serve", help="run the website, Telegram webhook, X poller and workers")
    a = p.parse_args(argv)
    handlers = {
        "migrate": _migrate,
        "read": _read,
        "tg": _tg,
        "serve": _serve,
        "tarot": _tarot,
        "prophecy": _prophecy,
        "score": _score,
        "status": _status,
    }
    code = handlers[a.cmd](a)
    if asyncio.iscoroutine(code):
        code = asyncio.run(code)
    sys.exit(code or 0)


if __name__ == "__main__":
    run()
