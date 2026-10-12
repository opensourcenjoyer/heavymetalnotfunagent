"""Rich renderers for signals, Trenches / Fear & Greed, the scanner, connectors and the wiki."""

from __future__ import annotations

import datetime as dt
import json
import time

from rich import box
from rich.columns import Columns
from rich.console import Group
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from heavymetal.trenches.fear_greed import BANDS, band
from heavymetal.ui import console

SPARK = "▁▂▃▄▅▆▇█"
VERDICT_COLOR = {
    "HIGH_CONVICTION": "bold green",
    "SPECULATIVE": "yellow",
    "HIGH_RISK": "red",
    "FARM": "bold magenta",
    "HONEYPOT": "bold red",
    "FAKE": "bold red",
}
STATE_STYLE = {
    "running": "green",
    "cooling": "yellow",
    "falling": "red",
    "dead": "dim",
    "rugged": "bold red",
    "n/a": "dim",
}
SOURCE_STYLE = {"dune": "cyan", "gt": "green", "est": "grey50"}
NA = "[dim]n/a[/dim]"


# ---------------------------------------------------------------- formatting
def usd(v, digits: int = 1) -> str:
    if v is None:
        return "n/a"
    a = abs(v)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"${v / div:.{digits}f}{suf}"
    return f"${v:,.0f}"


def pct(v, signed: bool = True, color: bool = True) -> str:
    if v is None:
        return NA
    s = f"{v:+.1f}%" if signed else f"{v:.1f}%"
    if not color:
        return s
    return f"[green]{s}[/green]" if v > 0 else f"[red]{s}[/red]" if v < 0 else s


def share(v) -> str:
    return NA if v is None else f"{100 * v:.0f}%"


def mult(v) -> str:
    if v is None:
        return NA
    style = "bold green" if v >= 2 else "green" if v >= 1 else "red" if v < 0.5 else "yellow"
    return f"[{style}]{v:.2f}×[/{style}]"


def ago(ts: float | None) -> str:
    if not ts:
        return "never"
    s = time.time() - ts
    if s < 90:
        return f"{s:.0f}s ago"
    if s < 5400:
        return f"{s / 60:.0f}m ago"
    if s < 172800:
        return f"{s / 3600:.1f}h ago"
    return f"{s / 86400:.1f}d ago"


def spark(vals: list[float | None], width: int = 48) -> str:
    vals = [v for v in vals if v is not None][-width:]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    return "".join(SPARK[min(7, int((v - lo) / rng * 7.999))] for v in vals)


def spark_sources(rows: list[dict], width: int = 60) -> Text:
    rows = [r for r in rows if r.get("smallcap")][-width:]
    t = Text()
    if not rows:
        return t
    vals = [r["smallcap"] for r in rows]
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    for r in rows:
        t.append(SPARK[min(7, int((r["smallcap"] - lo) / rng * 7.999))], style=SOURCE_STYLE.get(r["source"], "white"))
    return t


def verdict_txt(v: str | None) -> str:
    if not v:
        return NA
    return f"[{VERDICT_COLOR.get(v, 'white')}]{v}[/{VERDICT_COLOR.get(v, 'white')}]"


# ---------------------------------------------------------------- fear & greed
def gauge(idx: float | None, width: int = 50) -> Text:
    t = Text()
    lo = 0
    for hi, _word, color in BANDS:
        n = round((hi - lo) / 100 * width)
        t.append("━" * n, style=color)
        lo = hi
    marker = Text(" " * width)
    if idx is not None:
        pos = min(width - 1, max(0, round(idx / 100 * (width - 1))))
        marker = Text(" " * pos + "▲", style="bold white")
    scale = Text("0" + " " * (width // 2 - 2) + "50" + " " * (width - width // 2 - 3) + "100", style="dim")
    return Text.assemble(t, "\n", marker, "\n", scale)


def microbar(v: float | None, width: int = 20) -> Text:
    if v is None:
        return Text("n/a", style="dim")
    n = round(v / 100 * width)
    _, color = band(v)
    return Text.assemble(("█" * n, color), ("░" * (width - n), "grey23"), (f" {v:.0f}", "bold"))


def render_fear_greed(fg: dict, history: list[dict] | None = None) -> Panel:
    idx = fg.get("index")
    word, color = band(idx)
    big = Text(f"{idx}" if idx is not None else "n/a", style=f"bold {color}")
    big.append(f"  {word if idx is not None else 'INDEX WITHHELD'}", style=color if idx is not None else "dim")
    arms = Table.grid(padding=(0, 2))
    arms.add_column(style="dim")
    arms.add_column()
    arms.add_column(style="dim")
    W = fg.get("weights") or {}
    raw = fg.get("raw") or {}
    labels = {
        "volume": ("Smallcap volume", usd(raw.get("volume")) + " vs " + usd((fg.get("normals") or {}).get("volume"))),
        "momentum": ("Volume momentum", f"7d/7d {raw['momentum']:.2f}×" if raw.get("momentum") else "n/a"),
        "hold": ("Hold ladder", f"depth {raw['hold']:.3f}" if raw.get("hold") is not None else "n/a"),
        "ceiling": ("Ceiling ladder", f"depth {raw['ceiling']:.3f}" if raw.get("ceiling") is not None else "n/a"),
    }
    for k, (lab, detail) in labels.items():
        arms.add_row(f"{lab} · {round(100 * W.get(k, 0))}%", microbar((fg.get("arms") or {}).get(k)), detail)
    parts = [big, gauge(idx), Text(""), arms]
    hist = [h.get("idx") for h in (history or []) if h.get("idx") is not None]
    if len(hist) >= 2:
        parts.append(Text.assemble(("history ", "dim"), (spark(hist, 30), color), (f"  {len(hist)}d", "dim")))
    parts.append(Text(f"scored launches: {fg.get('cohort', 0)} (needs {fg.get('min_tapes', 8)})", style="dim"))
    for n in fg.get("notes") or []:
        parts.append(Text(f"· {n}", style="dim italic"))
    return Panel(
        Group(*parts),
        title="[bold]Trench Fear & Greed[/bold]",
        subtitle="[dim]smallcap volume first, against fixed normals[/dim]",
        border_style=color,
        padding=(0, 1),
    )


# ---------------------------------------------------------------- trenches
def render_trenches(p: dict) -> None:
    t = p.get("today") or {}
    d = p.get("deltas") or {}
    rg = p.get("regime") or {}
    head = Table.grid(padding=(0, 3))
    for _ in range(4):
        head.add_column()
    head.add_row(
        Text.assemble(("SMALLCAP 24H\n", "dim"), (usd(t.get("smallcap_vol")), "bold white")),
        Text.assemble(("TRENCH 24H (ex top-5)\n", "dim"), (usd(t.get("trench_vol")), "bold white")),
        Text.assemble(("PACE 6H×4\n", "dim"), (f"{t['pace']:.2f}×" if t.get("pace") else "n/a", "bold")),
        Text.assemble(("COVERAGE of chain DEX vol\n", "dim"), (share(t.get("coverage")), "bold")),
    )
    head.add_row(
        Text.from_markup(f"[dim]d/d[/dim] {pct(d.get('d1'))}   [dim]w/w[/dim] {pct(d.get('w1'))}"),
        Text.from_markup(f"[dim]top-5 share[/dim] {share(t.get('top5_share'))}"),
        Text.from_markup(f"[dim]EMA7[/dim] {usd(p.get('ema7'))}  [dim]EMA14[/dim] {usd(p.get('ema14'))}"),
        Text.from_markup(
            f"[dim]source[/dim] {t.get('source', 'n/a')} · {t.get('kept', 0)}/{t.get('pools', 0)} pools kept"
        ),
    )
    reg_style = {
        "hot": "bold green",
        "warming": "green",
        "normal": "white",
        "cooling": "yellow",
        "cold": "bold red",
    }.get(rg.get("label"), "dim")
    regime = Text.assemble(
        ("REGIME ", "dim"),
        (str(rg.get("label", "n/a")).upper(), reg_style),
        ("   percentile vs own history: ", "dim"),
        f"90d {rg.get('90', 'n/a')}  180d {rg.get('180', 'n/a')}  1y {rg.get('365', 'n/a')}",
    )
    series = p.get("series") or []
    sp = Group(
        Text.assemble(("Total smallcap volume, daily ", "dim"), (f"({len(series)}d)", "dim")),
        spark_sources(series, 90),
        Text.assemble(("■ dune  ", "cyan"), ("■ sweep  ", "green"), ("■ estimate (DefiLlama × share)", "grey50")),
    )
    console.print(
        Panel(
            Group(head, Text(""), regime, Text(""), sp),
            title="[bold]Trench Pulse · Solana[/bold]",
            subtitle="[dim]smallcaps ≤ $200M · majors, stables, equities & farms excluded[/dim]",
            border_style="magenta",
        )
    )

    top = Table(title="Top tickers", box=box.SIMPLE_HEAD, header_style="bold magenta", title_style="bold")
    top.add_column("#", style="dim")
    top.add_column("ticker")
    top.add_column("24h vol", justify="right")
    top.add_column("share", justify="right")
    for i, r in enumerate(t.get("top5") or [], 1):
        top.add_row(str(i), escape(str(r["symbol"])), usd(r["vol"]), share(r["share"]))
    drops = Table(title="Gates & drops", box=box.SIMPLE_HEAD, header_style="bold magenta", title_style="bold")
    drops.add_column("gate")
    drops.add_column("pools", justify="right")
    drops.add_column("volume", justify="right")
    for k, v in sorted((t.get("drops") or {}).items(), key=lambda kv: -kv[1]["vol"]):
        style = "magenta" if k not in ("major", "megacap", "equity") else "dim"
        drops.add_row(f"[{style}]{k}[/{style}]", str(v["n"]), usd(v["vol"]))
    lad = p.get("launches") or {}
    ladt = Table(
        title=f"Launch ladders (n={lad.get('cohort', 0)}{' · thin' if lad.get('thin') else ''})",
        box=box.SIMPLE_HEAD,
        header_style="bold magenta",
        title_style="bold",
    )
    ladt.add_column("tier")
    ladt.add_column("holding", justify="right")
    ladt.add_column("topped", justify="right")
    for tier in (2, 3, 5, 7, 10):
        h = (lad.get("hold") or {}).get(tier, (lad.get("hold") or {}).get(str(tier)))
        c = (lad.get("ceiling") or {}).get(tier, (lad.get("ceiling") or {}).get(str(tier)))
        ladt.add_row(f"≥{tier}× D1", share(h), share(c))
    console.print(Columns([top, drops, ladt], padding=(0, 4)))
    if p.get("dune"):
        du = p["dune"]
        console.print(
            f"[cyan]Dune · {du.get('day')}[/cyan] full population: smallcap {usd(du.get('smallcap_vol'))}, trench "
            f"{usd(du.get('trench_vol'))}, read {du.get('rows_read')}/{du.get('rows_total') or '?'} rows"
            + ("" if du.get("complete") else " [yellow](partial)[/yellow]")
        )
    console.print(render_fear_greed(p.get("fear_greed") or {}, p.get("fg_history")))
    for n in [n for n in p.get("notes") or [] if n not in ((p.get("fear_greed") or {}).get("notes") or [])]:
        console.print(f"[dim]· {n}[/dim]")
    console.print(
        f"[dim]as of {dt.datetime.fromtimestamp(p.get('as_of', time.time())):%H:%M:%S} · "
        "analysis only, not financial advice · /wiki trenches/methodology[/dim]"
    )


# ---------------------------------------------------------------- signals
def render_runners(rows: list[dict], title: str = "Runners · since first call") -> None:
    if not rows:
        console.print("[dim]no signals match (the scanner fills this; /scanner status)[/dim]")
        return
    t = Table(title=title, box=box.SIMPLE_HEAD, header_style="bold magenta", title_style="bold")
    for c, j in (
        ("#", "right"),
        ("token", "left"),
        ("verdict", "left"),
        ("state", "left"),
        ("since call", "right"),
        ("peak", "right"),
        ("milestone", "left"),
        ("1h", "right"),
        ("24h", "right"),
        ("FDV", "right"),
        ("liq", "right"),
        ("age", "right"),
    ):
        t.add_column(c, justify=j, style="dim" if c == "#" else None)
    for r in rows:
        st = STATE_STYLE.get(r["state"], "white")
        badge = f"[bold black on yellow] {r['top_level']}× [/]" if r.get("top_level") else ""
        t.add_row(
            str(r["id"]),
            f"[bold]{escape(r['symbol'] or '?')}[/bold] [dim]{r['mint'][:4]}…{r['mint'][-4:]}[/dim]",
            verdict_txt(r["verdict"])
            + ("" if r["verdict_now"] == r["verdict"] else f" [dim]→{r['verdict_now']}[/dim]"),
            f"[{st}]{r['state']}[/{st}]",
            mult(r["multiple"]),
            mult(r["peak"]),
            badge,
            pct(r["chg_h1"]),
            pct(r["chg_h24"]),
            usd(r["fdv"]),
            usd(r["liq"]),
            f"{r['age_h']:.0f}h" if r["age_h"] < 72 else f"{r['age_h'] / 24:.1f}d",
        )
    console.print(t)
    console.print(
        "[dim]multiple = current FDV ÷ FDV at the call (valuation, not a price return) · liq ≥ $25K · "
        "/signals <id> for detail[/dim]"
    )


def _rate(row: dict, w: str) -> str:
    v, n = row.get(f"hit_{w}"), row.get(f"n_{w}", 0)
    if v is None:
        return f"{NA} [dim]n=0[/dim]"
    thin = " [yellow]thin[/yellow]" if row.get(f"thin_{w}") else ""
    return f"{100 * v:.0f}% [dim]n={n}[/dim]{thin}"


def render_performance(perf: dict) -> None:
    lv = perf.get("level", 2)
    t = Table(
        title=f"Signal performance · hit = reached {lv}× after the call",
        box=box.SIMPLE_HEAD,
        header_style="bold magenta",
        title_style="bold",
    )
    for c in ("entry verdict", "n", "≤24h", "≤72h", "≤7d", "median now", "median peak", "best", "died", "rugged"):
        t.add_column(c, justify="left" if c == "entry verdict" else "right")

    def add(label, r, style=None):
        t.add_row(
            label if not style else f"[{style}]{label}[/{style}]",
            str(r["n"]) + (" [yellow]thin[/yellow]" if r.get("thin") else ""),
            _rate(r, "24h"),
            _rate(r, "72h"),
            _rate(r, "7d"),
            mult(r.get("median_multiple")),
            mult(r.get("median_peak")),
            mult(r.get("best_peak")),
            share(r.get("dead")),
            share(r.get("rugged")),
        )

    for r in perf.get("rows") or []:
        add(r["verdict"], r, VERDICT_COLOR.get(r["verdict"]))
    s = perf.get("summary") or {}
    if s:
        t.add_section()
        add("tradeable (HC+SPEC)", s["tradeable"], "bold")
        add("filtered out (HARD PASS)", s["filtered_out"], "dim")
        add("all", s["all"])
    console.print(t)
    console.print(
        "[dim]windows count only signals old enough to have lived through them · thin = n<5 · n/a = no data, "
        "never zero · a good filter shows filtered-out rows dying more and hitting less[/dim]"
    )


def render_backtest(bt: dict) -> None:
    g = bt.get("guards") or {}
    guards = " · ".join(f"{k}={v}" for k, v in g.items())
    if bt.get("status") != "ok":
        console.print(
            Panel(
                f"{bt.get('note', 'insufficient data')}\n[dim]leak guards: {guards}[/dim]",
                title=f"Backtest · {bt['horizon_h']:.0f}h · {bt['level']}×",
                border_style="yellow",
            )
        )
        return
    t = Table(
        title=f"Walk-forward backtest · label = {bt['level']}× within {bt['horizon_h']:.0f}h · n={bt['n']} · "
        f"base rate {share(bt.get('base_rate'))}",
        box=box.SIMPLE_HEAD,
        header_style="bold magenta",
    )
    for c in ("model", "AUC", "precision", "recall", "lift"):
        t.add_column(c, justify="right" if c != "model" else "left")
    for name, m in (bt.get("models") or {}).items():
        t.add_row(
            name,
            str(m["auc"] if m["auc"] is not None else "n/a"),
            share(m["precision"]),
            share(m["recall"]),
            f"{m['lift']}×" if m.get("lift") else "n/a",
        )
    console.print(t)
    ft = Table(box=box.MINIMAL, header_style="dim")
    for c in ("fold", "train", "test", "base", "rules AUC", "logit AUC"):
        ft.add_column(c, justify="right")
    for i, f in enumerate(bt.get("folds") or [], 1):
        ft.add_row(
            str(i),
            str(f["train"]),
            str(f["test"]),
            share(f["base_rate"]),
            str(f["rules"]["auc"] or "n/a"),
            str(f["logit"]["auc"] or "n/a"),
        )
    console.print(ft)
    if bt.get("weights"):
        console.print(
            "[dim]logit top weights (standardised):[/dim] "
            + ", ".join(f"{k} {'+' if w > 0 else ''}{w}" for k, w in bt["weights"])
        )
    console.print(f"[dim]leak guards: {guards} · split by time, scaling fit on train only[/dim]")


def render_signal_detail(sig: dict, marks: list[dict], ms: list[dict]) -> None:
    from heavymetal.signals.ledger import multiple, state

    m = multiple(sig)
    feats = json.loads(sig.get("features") or "{}")
    body = Table.grid(padding=(0, 2))
    body.add_column(style="dim")
    body.add_column()
    body.add_row("mint", sig["mint"])
    body.add_row(
        "called", f"{dt.datetime.fromtimestamp(sig['ts']):%Y-%m-%d %H:%M} ({ago(sig['ts'])}) via {sig['source']}"
    )
    body.add_row("verdict", verdict_txt(sig["verdict"]) + f"  [dim]now:[/dim] {verdict_txt(sig['verdict_now'])}")
    body.add_row("at call", f"FDV {usd(sig['fdv0'])} · liq {usd(sig['liq0'])} · price {sig['price0']}")
    body.add_row("now", f"FDV {usd(sig['last_fdv'])} · liq {usd(sig['last_liq'])} · {mult(m)} · {state(sig)}")
    body.add_row(
        "peak",
        f"{usd(sig['peak_fdv'])} ({mult(sig['peak_fdv'] / sig['fdv0'] if sig.get('peak_fdv') and sig.get('fdv0') else None)})",
    )
    body.add_row(
        "milestones",
        " ".join(
            f"[bold black on yellow] {x['level']}× [/] [dim]{ago(x['ts'])}"
            f"{' first-observed' if x['first_observed'] else ''}[/dim]"
            for x in ms
        )
        or "none",
    )
    body.add_row("reasons", escape("; ".join(json.loads(sig.get("reasons") or "[]"))[:300]) or "-")
    body.add_row(
        "features",
        Text(", ".join(f"{k}={v}" for k, v in feats.items() if k not in ("as_of", "v") and v is not None)[:400]),
    )
    fdvs = [x["fdv"] for x in marks if x.get("fdv")]
    if len(fdvs) > 1:
        body.add_row("FDV path", Text(spark(fdvs, 60), style="cyan"))
    console.print(
        Panel(body, title=f"[bold]signal #{sig['id']} · {escape(str(sig['symbol']))}[/bold]", border_style="magenta")
    )


def render_scanner(st: dict) -> None:
    s = st.get("stats") or {}
    dot = "[green]●[/green]" if st.get("running") else "[red]●[/red]"
    ws = "[green]connected[/green]" if st.get("ws_connected") else "[yellow]reconnecting[/yellow]"
    g = Table.grid(padding=(0, 2))
    g.add_column(style="dim")
    g.add_column()
    g.add_row("status", f"{dot} {'running' if st.get('running') else 'stopped'} · since {ago(st.get('since'))}")
    g.add_row(
        "feeds",
        f"PumpPortal ws {ws} ({s.get('ws_seen', 0)} seen) · GeckoTerminal new pools ({s.get('gt_seen', 0)} seen, {ago(st.get('last_scan'))})",
    )
    g.add_row(
        "pipeline",
        f"{st.get('pending', 0)} pending re-checks · {st.get('queued', 0)} queued · {s.get('audited', 0)} audited",
    )
    g.add_row(
        "recorded",
        f"{s.get('signals', 0)} signals · {s.get('farms', 0)} farms · {s.get('milestones', 0)} milestones · "
        f"{s.get('marks', 0)} marks ({ago(st.get('last_mark'))})",
    )
    today = st.get("today") or {}
    g.add_row("last 24h", " · ".join(f"{verdict_txt(k)} {v}" for k, v in today.items()) or "none yet")
    g.add_row("trenches", f"refreshed {ago(st.get('last_pulse'))}")
    if st.get("last_error"):
        g.add_row("last error", f"[yellow]{st['last_error']}[/yellow]")
    console.print(Panel(g, title="[bold]Scanner[/bold]", border_style="magenta"))
    for a in (st.get("recent_alerts") or [])[-6:]:
        console.print(alert_text(a))


def render_connectors(rows: list[dict]) -> None:
    t = Table(title="Data connectors", box=box.SIMPLE_HEAD, header_style="bold magenta", title_style="bold")
    for c in ("", "name", "key", "unlocks", "get a key"):
        t.add_column(c)
    for r in rows:
        dot = "[green]●[/green]" if r["configured"] else "[dim]○[/dim]"
        key = "[dim]keyless[/dim]" if r["keyless"] else (r["value"] or "[yellow]not set[/yellow]")
        t.add_row(dot, r["name"], key, r["unlocks"], f"[dim]{r['signup']}[/dim]")
    console.print(t)
    console.print("[dim]/keys set <name> (hidden input) · /keys rm <name> · env vars override the file[/dim]")


# ---------------------------------------------------------------- wiki
def _snip(s: str) -> str:
    s = " ".join(s.split())
    return escape(s).replace("«", "[bold yellow]").replace("»", "[/bold yellow]")


def render_wiki_results(rows: list[dict], query: str) -> None:
    if not rows:
        console.print(f"[dim]no wiki pages for '{query}' · /wiki for the index[/dim]")
        return
    t = Table(title=f"wiki · {query}", box=box.SIMPLE_HEAD, header_style="bold magenta", title_style="bold")
    t.add_column("page", style="cyan")
    t.add_column("summary / match")
    for r in rows:
        t.add_row(
            r["slug"] + (" [dim](yours)[/dim]" if r.get("origin") == "user" else ""),
            f"[bold]{escape(r['title'])}[/bold]\n[dim]{_snip(r.get('snippet') or r.get('summary') or '')}[/dim]",
        )
    console.print(t)


def render_wiki_page(p: dict) -> None:
    head = f"[dim]{p['slug']} · {p.get('tags', '')}[/dim]"
    if p.get("verify"):
        head += f"\n[yellow]verify: {p['verify']}[/yellow]"
    console.print(
        Panel(
            Group(Text.from_markup(head), Markdown(p["body"])), title=f"[bold]{p['title']}[/bold]", border_style="cyan"
        )
    )


def render_wiki_index(rows: list[dict]) -> None:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["slug"].split("/")[0] if "/" in r["slug"] else "·", []).append(r)
    t = Table(box=box.SIMPLE_HEAD, header_style="bold magenta", title="agent wiki", title_style="bold")
    t.add_column("section", style="magenta")
    t.add_column("page", style="cyan")
    t.add_column("summary", style="dim")
    for g, items in groups.items():
        for i, r in enumerate(items):
            t.add_row(g if i == 0 else "", r["slug"], escape(r["summary"][:90]))
    console.print(t)
    console.print("[dim]/wiki <query> search · /wiki <slug> read · your notes: ~/.heavymetal/wiki[/dim]")


# ---------------------------------------------------------------- alerts & toolbar
def alert_text(a: dict) -> Text:
    k = a.get("kind")
    tstr = dt.datetime.fromtimestamp(a.get("ts", time.time())).strftime("%H:%M")
    if k == "signal":
        style = VERDICT_COLOR.get(a.get("verdict"), "white")
        return Text.from_markup(
            f"[dim]{tstr}[/dim] [bold magenta]◆ signal[/bold magenta] [bold]{escape(str(a.get('symbol') or '?'))}[/bold] "
            f"[{style}]{a.get('verdict')}[/{style}] FDV {usd(a.get('fdv'))} · liq {usd(a.get('liq'))} · "
            f"vol {usd(a.get('vol_h24'))} [dim]{a.get('source')} · #{a.get('id')} · {escape(str(a.get('reason') or '')[:60])}[/dim]"
        )
    if k == "milestone":
        return Text.from_markup(
            f"[dim]{tstr}[/dim] [bold black on yellow] {a.get('level')}× [/] [bold]{escape(str(a.get('symbol')))}[/bold] "
            f"since call ({verdict_txt(a.get('verdict'))}) FDV {usd(a.get('fdv'))} [dim]#{a.get('id')}[/dim]"
        )
    if k == "signal_end":
        return Text.from_markup(
            f"[dim]{tstr}[/dim] [red]✖ {escape(str(a.get('symbol')))} {a.get('status')}[/red] "
            f"[dim]({a.get('verdict')}, #{a.get('id')}, post-mortem in /wiki cases)[/dim]"
        )
    if k == "pulse":
        word, color = band(a.get("index"))
        return Text.from_markup(
            f"[dim]{tstr}[/dim] [dim]trenches:[/dim] F&G [{color}]{a.get('index') if a.get('index') is not None else 'n/a'} "
            f"{word}[/{color}] · smallcap {usd(a.get('smallcap'))}"
        )
    return Text(f"{tstr} {k}: {a}")


def toolbar(env):
    """prompt_toolkit bottom toolbar: F&G, smallcap volume, scanner, today's signals, last milestone."""
    from heavymetal.trenches.pulse import cached

    parts: list[tuple[str, str]] = []
    p = cached(env)
    if p:
        fg = p.get("fear_greed") or {}
        idx = fg.get("index")
        word, _ = band(idx)
        colors = {
            "EXTREME FEAR": "#ff5f5f",
            "FEAR": "#ff8700",
            "NEUTRAL": "#a8a8a8",
            "GREED": "#5fd75f",
            "EXTREME GREED": "#5fd7d7",
            "N/A": "#808080",
        }
        parts.append(
            (f"bg:#1c1c1c fg:{colors.get(word, '#a8a8a8')} bold", f" F&G {idx if idx is not None else 'n/a'} {word} ")
        )
        t = p.get("today") or {}
        d1 = (p.get("deltas") or {}).get("d1")
        parts.append(
            (
                "bg:#1c1c1c fg:#d0d0d0",
                f"│ smallcap {usd(t.get('smallcap_vol'))}"
                + (f" {'▲' if d1 > 0 else '▼'}{abs(d1):.0f}%" if d1 is not None else "")
                + " ",
            )
        )
        parts.append(("bg:#1c1c1c fg:#d0d0d0", f"│ {(p.get('regime') or {}).get('label', 'n/a')} "))
    else:
        parts.append(("bg:#1c1c1c fg:#808080", " F&G … "))
    sc = getattr(env, "scanner", None)
    if sc is not None and sc.running:
        s = sc.stats
        parts.append(("bg:#1c1c1c fg:#5fd75f", "│ scanner ● "))
        parts.append(
            ("bg:#1c1c1c fg:#d0d0d0", f"{s['signals']} signals · {s['farms']} farms · {len(sc.pending)} pending ")
        )
        last = next((a for a in reversed(sc.alerts) if a["kind"] == "milestone"), None)
        if last:
            parts.append(("bg:#1c1c1c fg:#ffd700 bold", f"│ last {last['level']}×: {last.get('symbol')} "))
    else:
        parts.append(("bg:#1c1c1c fg:#808080", "│ scanner off "))
    return parts
