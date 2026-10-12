"""REPL commands: /trenches /fg /signals /scanner /wiki /keys, plus the scanner alert sink."""

from __future__ import annotations

from rich.markup import escape

from heavymetal import config as config_mod
from heavymetal.ui import console
from heavymetal.ui_signals import (
    alert_text,
    render_backtest,
    render_connectors,
    render_fear_greed,
    render_performance,
    render_runners,
    render_scanner,
    render_signal_detail,
    render_trenches,
    render_wiki_index,
    render_wiki_page,
    render_wiki_results,
)

TRENCHES_HELP = "/trenches [refresh | sql | calibrate [save]]   /fg"
SIGNALS_HELP = (
    "/signals [runners [24h|72h|all] | perf [days] | backtest [hours] | backfill | farms | recent | <id|mint|symbol>]"
)


class AlertSink:
    """Scanner alerts print above the prompt while idle; during an agent turn they wait and print after it."""

    def __init__(self):
        self.busy = False
        self.buffer: list[dict] = []

    def __call__(self, kind: str, item: dict) -> None:
        if kind == "pulse":  # shown in the toolbar; don't spam the scrollback
            return
        if self.busy:
            self.buffer.append(item)
        else:
            console.print(alert_text(item))

    def flush(self) -> None:
        items, self.buffer = self.buffer, []
        for a in items[-12:]:
            console.print(alert_text(a))
        if len(items) > 12:
            console.print(f"[dim]… {len(items) - 12} more alerts · /scanner[/dim]")


def start_scanner(env, sink=None) -> str:
    from heavymetal.signals.scanner import Scanner

    if env.scanner is None:
        env.scanner = Scanner(env, on_alert=sink)
    elif sink is not None:
        env.scanner.on_alert = sink
    if env.scanner.start():
        return "scanner ● running: PumpPortal launches + GeckoTerminal new pools, audits in code, never trades"
    return f"scanner not started: {env.scanner.last_error}"


async def trenches_cmd(env, rest: list[str]) -> None:
    from heavymetal.trenches import pulse

    sub = rest[0] if rest else ""
    if sub == "sql":
        from heavymetal.data.dune import TRENCHES_SQL

        console.print(TRENCHES_SQL, markup=False, highlight=False)
        console.print(
            "[dim]1) paste into a new query on dune.com, run it, schedule it daily (after 00:15 UTC)\n"
            "2) /keys set dune   3) /keys set dune_query_id  (the number in the query URL)[/dim]"
        )
        return
    if sub == "calibrate":
        from heavymetal.trenches.fear_greed import calibrate

        ser = [r for r in pulse.series(env.db) if r["source"] in ("gt", "dune")] or pulse.series(env.db)
        hist = [dict(r) for r in env.db.conn.execute("SELECT hold_depth, ceiling_depth FROM fg_days")]
        sug = calibrate(ser, [h["hold_depth"] for h in hist], [h["ceiling_depth"] for h in hist])
        console.print(
            f"suggested normals from {sug['days']} days of volume and {sug['hold_days']} days of ladders:\n"
            f"  fg_volume_normal = {sug['fg_volume_normal']}\n  fg_hold_normal = {sug['fg_hold_normal']}\n"
            f"  fg_ceiling_normal = {sug['fg_ceiling_normal']}"
        )
        if len(rest) > 1 and rest[1] == "save":
            for k in ("fg_volume_normal", "fg_hold_normal", "fg_ceiling_normal"):
                if sug[k]:
                    setattr(env.cfg.signals, k, float(sug[k]))
            config_mod.save(env.cfg)
            console.print("[green]saved to [signals] in config.toml[/green]")
        elif sug["days"] < 30:
            console.print("[yellow]fewer than 30 measured days: keep the defaults for now[/yellow]")
        return
    if env.cluster != "mainnet":
        console.print("[yellow]trenches reads mainnet market data; switch with /rpc use <mainnet node>[/yellow]")
    force = sub == "refresh"
    if not force and pulse.cached(env) is None:
        console.print("[dim]first sweep reads ~10 GeckoTerminal pages + launch candles (public API, ~1 min)[/dim]")
    with console.status("sweeping Solana pools through the gates…"):
        p = await pulse.refresh(env, force=force)
    render_trenches(p)


async def fg_cmd(env) -> None:
    from heavymetal.trenches import pulse

    p = pulse.cached(env)
    if p is None:
        with console.status("sweeping…"):
            p = await pulse.refresh(env)
    console.print(render_fear_greed(p["fear_greed"], p.get("fg_history")))


async def signals_cmd(env, rest: list[str]) -> None:
    from heavymetal.signals import ledger, performance

    sub = rest[0] if rest else "runners"
    if sub == "runners":
        win = {"24h": 24, "72h": 72, "7d": 168, "all": None}.get(rest[1] if len(rest) > 1 else "all")
        render_runners(
            performance.runners(env.db, 25, env.cfg.signals.milestone_min_liq, win),
            f"Runners · {'all' if not win else rest[1]} · since first call",
        )
    elif sub == "recent":
        rows = performance.runners(env.db, 25, 0, None, rank="multiple")
        rows.sort(key=lambda r: r["age_h"])
        render_runners(rows, "Recent signals (any liquidity)")
    elif sub == "farms":
        rows = [r for r in performance.runners(env.db, 200, 0) if r["verdict"] == "FARM" or r["verdict_now"] == "FARM"]
        render_runners(rows[:25], "Farm-flagged signals (did the filter remove winners?)")
    elif sub in ("perf", "performance"):
        days = float(rest[1]) if len(rest) > 1 else None
        render_performance(performance.performance(env.db, days))
    elif sub == "backtest":
        from heavymetal.signals.backtest import backtest

        h = float(rest[1]) if len(rest) > 1 else 72
        render_backtest(backtest(env.db, h))
    elif sub == "backfill":
        from heavymetal.signals.backtest import backfill_outcomes

        with console.status("backfilling outcomes from GeckoTerminal hourly candles…"):
            r = await backfill_outcomes(env, limit=40)
        console.print(f"backfilled {r['signals']} signals: {r['marks']} hourly marks, {r['milestones']} new milestones")
    else:
        sig = ledger.get_signal(env.db, sub)
        if not sig:
            console.print(f"no signal '{escape(sub)}' · {escape(SIGNALS_HELP)}")
            return
        marks = [
            dict(r)
            for r in env.db.conn.execute("SELECT * FROM signal_marks WHERE signal_id=? ORDER BY ts", (sig["id"],))
        ]
        ms = [
            dict(r)
            for r in env.db.conn.execute("SELECT * FROM milestones WHERE signal_id=? ORDER BY level", (sig["id"],))
        ]
        render_signal_detail(sig, marks, ms)


async def scanner_cmd(env, rest: list[str], sink=None) -> None:
    sub = rest[0] if rest else "status"
    if sub == "on":
        env.cfg.signals.scanner = True
        config_mod.save(env.cfg)
        console.print(start_scanner(env, sink))
    elif sub == "off":
        env.cfg.signals.scanner = False
        config_mod.save(env.cfg)
        if env.scanner:
            await env.scanner.stop()
        console.print("scanner stopped (stays off across restarts; /scanner on)")
    elif sub == "mark":
        if env.scanner is None:
            console.print("scanner not running")
            return
        with console.status("marking tracked signals…"):
            r = await env.scanner.mark_once()
        console.print(f"marked {r['marked']} signals")
    else:
        if env.scanner is None:
            console.print(f"scanner not started · /scanner on (mainnet) · enabled in config: {env.cfg.signals.scanner}")
            return
        render_scanner(env.scanner.status())


def wiki_cmd(env, rest: list[str]) -> None:
    from heavymetal.kb.wiki import get_wiki

    w = get_wiki()
    if not rest:
        render_wiki_index(w.index())
        return
    if rest[0] == "reload":
        w.load()
        console.print(f"wiki reloaded: {len(w.pages)} pages")
        return
    q = " ".join(rest)
    page = w.read(q) if len(rest) == 1 else None
    if page:
        render_wiki_page(page)
    else:
        render_wiki_results(w.search(q), q)


async def keys_cmd(env, rest: list[str]) -> None:
    from prompt_toolkit import PromptSession

    from heavymetal.data.connectors import BY_NAME, KEYED, status

    sub = rest[0] if rest else ""
    if sub in ("set", "rm") and len(rest) == 2:
        c = BY_NAME.get(rest[1])
        if not c or not c.key_field:
            console.print(f"unknown key '{rest[1]}'; one of: {', '.join(KEYED)}")
            return
        if sub == "rm":
            setattr(env.cfg.keys, c.key_field, "")
        else:
            console.print(f"[dim]{c.name}: {c.unlocks}. Get one at {c.signup}[/dim]")
            try:
                val = await PromptSession().prompt_async(
                    f"{c.name} {'key' if c.secret else 'value'}: ", is_password=c.secret
                )
            except (KeyboardInterrupt, EOFError):
                console.print("cancelled")
                return
            val = val.strip()
            if not val:
                console.print("empty, nothing saved")
                return
            setattr(env.cfg.keys, c.key_field, val)
        config_mod.save(env.cfg)
        console.print(
            f"[green]{c.name} {'removed' if sub == 'rm' else 'saved'}[/green] (~/.heavymetal/config.toml, chmod 600)"
            + (f" · env var {c.env_var} overrides it" if c.env_var else "")
        )
        if c.name.startswith("dune"):
            from heavymetal.trenches import pulse

            pulse._cache.clear()
        return
    render_connectors(status(env.cfg))
