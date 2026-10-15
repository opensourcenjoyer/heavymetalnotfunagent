"""Terminal rendering: StreamRenderer, banner, tables, and reasoning blocks."""

from __future__ import annotations

import datetime as dt
import json
import time

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from heavymetal import mascot
from heavymetal.agent import short

console = Console()

BANNER = r"""[bold magenta]
 _                                         _        _
| |__   ___  __ ___   ___   _ _ __ ___   ___| |_ __ _| |
| '_ \ / _ \/ _` \ \ / / | | | '_ ` _ \ / _ \ __/ _` | |
| | | |  __/ (_| |\ V /| |_| | | | | | |  __/ || (_| | |
|_| |_|\___|\__,_| \_/  \__, |_| |_| |_|\___|\__\__,_|_|
                        |___/            agent for Solana[/bold magenta]"""

GOODBYE = "[dim]bye[/dim]"


def banner():
    """Startup banner: mascot beside the logo when there is room, above it on narrow terminals."""
    text = Text.from_markup(BANNER.strip("\n"))
    text.no_wrap = True
    if not mascot.enabled(console):
        return text
    logo_width = max(len(ln) for ln in text.plain.splitlines())
    if console.width >= mascot.WIDTH + 2 + logo_width:
        return mascot.beside(mascot.idle(), text)
    return Group(mascot.idle(), text)


VERDICT_STYLE = {"EXECUTE": "green", "REDUCE_SIZE": "yellow"}


class _WaitView:
    """Live renderable for the wait between prompt and reply: animated mascot, status, reasoning tail."""

    def __init__(self, renderer: StreamRenderer):
        self.r = renderer

    def __rich__(self):
        dots = "." * (int(time.monotonic() * 2) % 4)
        right = Text(no_wrap=False)
        right.append(f"{self.r.wait_label}{dots}\n", style="magenta")
        width = max(20, self.r.console.width - mascot.WIDTH - 2)
        tail = " ".join(self.r.reasoning_text.split())[-width * (mascot.HEIGHT - 3) :]
        if tail:
            right.append(("…" if len(tail) < len(self.r.reasoning_text) else "") + tail, style="dim italic")
        return mascot.beside(mascot.waiting(), right)


class StreamRenderer:
    """Streaming renderer with live Markdown parsing: incremental writes with full formatting.

    With the mascot on, the bear animates in a transient live view while the agent thinks or runs tools,
    then talks beside the reply while it streams (when the terminal is wide enough for both).
    """

    CONTENT_MIN_WIDTH = 60  # text column needed to stream the reply beside the mascot

    def __init__(self, console: Console, mascot_enabled: bool | None = None):
        self.console = console
        self.mascot = mascot.enabled(console) if mascot_enabled is None else mascot_enabled
        self.started = False
        self.in_reasoning = False
        self.reasoning_chars = 0
        self.content_chars = 0
        self.status = ""
        self.wait_label = "thinking"
        self._mute_reasoning = False
        self.reasoning_text = ""  # full reasoning, for the final block
        self.content_text = ""  # full streamed content
        self._seg_start = 0  # where the current live segment starts in content_text
        self._live = None
        self._wait = None

    def start(self):
        if not self.started:
            self.started = True
            self.in_reasoning = False
            self.content_chars = 0
            self._mute_reasoning = False
            self.reasoning_text = ""
            self.content_text = ""
            self._seg_start = 0
            self._live = None

    def waiting(self, label: str = "thinking"):
        """Show the animated mascot until text starts streaming (no-op without the mascot)."""
        self.start()
        self.wait_label = label
        if not self.mascot or self._wait is not None or self._live is not None:
            return
        self._wait = Live(
            _WaitView(self), console=self.console, refresh_per_second=mascot.FPS, transient=True, redirect_stderr=False
        )
        self._wait.start()

    def _stop_wait(self):
        if self._wait is not None:
            try:
                self._wait.stop()
            except Exception:  # noqa: BLE001
                pass
            self._wait = None

    def _stop_live(self, final: bool):
        if self._live is None:
            return
        try:
            if final and self._beside:  # leave the bear resting beside the finished text
                self._live.update(self._content_view(mascot.idle()), refresh=True)
            self._live.stop()
        except Exception:  # noqa: BLE001
            pass
        self._live = None

    def stop(self):
        self._stop_wait()
        if self._live is not None:
            self._stop_live(final=True)
        elif self.started and not self.streamed_anything:
            self.console.print()
        self.started = False
        self.in_reasoning = False

    def reset(self):
        self.stop()
        self.started = False
        self.in_reasoning = False
        self.reasoning_chars = 0
        self.content_chars = 0
        self.status = ""
        self.wait_label = "thinking"
        self._mute_reasoning = False
        self.reasoning_text = ""
        self.content_text = ""
        self._seg_start = 0
        self._live = None

    def on_delta(self, kind: str, text: str):
        if not text:
            return
        self.start()

        if kind == "reasoning":
            if self.content_chars or self._mute_reasoning:
                return
            if self._wait is not None:  # shown as a tail beside the mascot; full text goes in the final panel
                self.reasoning_text += text
                return
            if not self.in_reasoning:
                self.console.print("[dim italic]🧠 ", end="")
                self.in_reasoning = True
                self.reasoning_chars = 0
            self.console.print(
                text.replace("\n", " "),
                style="dim italic",
                end="",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
            self.reasoning_chars += len(text)
            self.reasoning_text += text
            if self.reasoning_chars > 2000:
                self.console.print(" …", style="dim italic", end="")
                self.in_reasoning = False
                self._mute_reasoning = True
            return

        if kind == "content":
            self._stop_wait()
            if self.in_reasoning:
                self.console.print("\n", end="")
                self.in_reasoning = False

            if self._live is None and self.console.is_terminal:
                self._seg_start = len(self.content_text)
                self._live = Live(console=self.console, auto_refresh=False, vertical_overflow="visible")
                self._live.start()

            self.content_text += text
            self.content_chars += len(text)

            if self._live is not None:
                self._live.update(self._content_view(mascot.talking() if self._beside else None), refresh=True)
            else:
                self.console.print(text, end="", markup=False, highlight=False, soft_wrap=True)

    @property
    def _beside(self) -> bool:
        return self.mascot and self.console.width >= mascot.WIDTH + 2 + self.CONTENT_MIN_WIDTH

    def _content_view(self, frame=None):
        md = Markdown(self.content_text[self._seg_start :])
        return mascot.beside(frame, md) if frame is not None else md

    def set_status(self, status: str):
        """Tool started (``status`` = tool name) or finished (empty): park the text, keep the bear busy."""
        self._stop_wait()
        self._stop_live(final=True)
        if status and self.status != status:
            self.console.print(f"[magenta]→ {status}[/magenta]")
        self.status = status
        if self.started:
            self.waiting(f"running {status}" if status else "thinking")

    @property
    def streamed_anything(self) -> bool:
        return self.content_chars > 0


# Backwards compatibility alias for Stream
Stream = StreamRenderer


def render_audit_card(data: dict) -> None:
    mint = data.get("mint", "")
    m = data.get("market") or {}
    s = data.get("safety") or {}
    h = data.get("holders") or {}
    verdict = data.get("verdict", "UNKNOWN")
    reasons = data.get("reasons", [])
    sym = m.get("symbol") or "TOKEN"

    price = f"${m['price_usd']:.6f}" if m.get("price_usd") else "N/A"
    liq = f"${m['liquidity_usd']:,.0f}" if m.get("liquidity_usd") else "N/A"
    fdv = f"${m['fdv']:,.0f}" if m.get("fdv") else "N/A"
    buy_ratio = m.get("buy_ratio_h1")
    ratio_str = (
        f"{int(buy_ratio * 100)}% Buys ({m.get('buys_h1', 0)}b/{m.get('sells_h1', 0)}s)"
        if buy_ratio is not None
        else "N/A"
    )
    freeze = "✓ Revoked" if not s.get("freeze_authority") else "✗ Active"
    mint_auth = "✓ Revoked" if not s.get("mint_authority") else "⚠ Active"
    lp_pct = s.get("lp_locked_pct")
    lp = (
        f"✓ {lp_pct:.0f}% Locked" if lp_pct and lp_pct > 80 else (f"⚠ {lp_pct:.0f}% Locked" if lp_pct else "⚠ Unlocked")
    )
    top10 = f"{h.get('top10_pct')}%" if h.get("top10_pct") is not None else "N/A"
    bubble_url = data.get("bubblemaps_url") or f"https://app.bubblemaps.io/sol/token/{mint}"

    v_color = (
        "green"
        if "BULLISH" in verdict or "APE" in verdict
        else ("yellow" if "SPECULATIVE" in verdict else ("magenta" if "FARM" in verdict else "red"))
    )
    farm = data.get("farm") or {}
    fm = farm.get("metrics") or {}
    turnover = f"{fm['turnover']:,.0f}x liq" if fm.get("turnover") is not None else "n/a"
    spw = (
        f"{fm['swaps_per_wallet']:.1f} swaps/wallet ({fm.get('swaps_per_wallet_source')})"
        if fm.get("swaps_per_wallet") is not None
        else "swaps/wallet n/a"
    )
    farm_state = (
        f"[bold magenta]FARM: {farm.get('kind')}[/bold magenta]"
        if farm.get("is_farm")
        else ("[yellow]⚠ churn[/yellow]" if farm.get("warnings") else "[green]✓ organic[/green]")
    )
    wiki = ", ".join(r["slug"] for r in data.get("wiki_refs") or [])
    sig = data.get("signal") or {}

    body = (
        f"[bold cyan]${sym}[/bold cyan] [dim]({mint[:6]}…{mint[-4:]})[/dim] | Venue: {(m.get('dex') or 'Solana').upper()}\n"
        f"Price: [bold]{price}[/bold] | Liq: {liq} | MC/FDV: {fdv}\n"
        f"1h Volume: ${m.get('volume_h1') or 0:,.0f} ({m.get('price_change_h1') or 0:+.1f}%) | Momentum: {ratio_str}\n"
        f"Safety: Mint: [{mint_auth}] | Freeze: [{freeze}] | LP: [{lp}]\n"
        f"Volume: {farm_state} | turnover {turnover} | {spw}\n"
        f"Holders: Top 10 hold {top10} | Bubblemaps: [link={bubble_url}]{bubble_url}[/link]\n\n"
        f"[bold {v_color}]VERDICT: {verdict}[/bold {v_color}]\n"
        + "\n".join(f" • {r}" for r in reasons[:3])
        + (f"\n[dim]wiki: {wiki}[/dim]" if wiki else "")
        + (
            f"\n[dim]signal #{sig.get('id')}{' (new)' if sig.get('new') else ''} · /signals {sig.get('id')}[/dim]"
            if sig
            else ""
        )
    )
    console.print(Panel(body, title=f"🎯 Token Radar - ${sym}", border_style="magenta"))


def make_event_handler(renderer: StreamRenderer, tool_log: list[str] | None = None):
    def on_event(kind: str, p: dict):
        if kind == "tool_start":
            name = p.get("name", "")
            renderer.set_status(name)
        elif kind == "tool_end":
            name = p.get("name", "")
            if name in ("token_audit", "degen_audit"):
                try:
                    d = json.loads(p.get("result", "{}"))
                    if d.get("status") == "success":
                        renderer.stop()
                        render_audit_card(d)
                except Exception:  # noqa: BLE001
                    pass
            res = short(p.get("result", ""))
            if tool_log is not None:
                tool_log.append(f"→ {name}\n← {res}")
            renderer.set_status("")
        elif kind == "rpc_failover":
            console.print(
                f"  [yellow]⇄ rpc: {p['from']} failed ({p['reason'][:80]}), now using {p['to']}[/yellow]",
                highlight=False,
            )
        elif kind == "review":
            v = p["verdict"]
            st = VERDICT_STYLE.get(v, "red")
            console.print(
                f"  [bold {st}]⚖ review ({p['model']}): {v}[/bold {st}] "
                f"[dim]{p['latency_s']}s ${p['cost_usd']:.5f} · {'; '.join(p['reasons'])[:160]}[/dim]",
                highlight=False,
            )

    return on_event


def render_markdown(text: str) -> None:
    if text and text.strip():
        console.print(Markdown(text))


def render_final(text: str, streamed: bool) -> None:
    if not streamed:
        render_markdown(text)


def ts(t: float) -> str:
    return dt.datetime.fromtimestamp(t).strftime("%m-%d %H:%M")


def table(title: str, cols: list[str], rows: list[list]) -> None:
    t = Table(title=title, show_lines=False, header_style="bold magenta")
    for c in cols:
        t.add_column(c, overflow="fold")
    for r in rows:
        t.add_row(*[("" if v is None else str(v)) for v in r])
    console.print(t)


def review_detail(r: dict) -> None:
    console.print(
        f"[bold]review #{r['id']}[/bold] {ts(r['ts'])}  {r['tool']}  → "
        f"[bold]{r['verdict']}[/bold]  ({r['model']}, {r['latency_s']}s, ${r['cost_usd'] or 0:.5f})"
    )
    console.print(f"  args: {r['args']}", highlight=False)
    for s in json.loads(r["steps"]):
        if s["step"] == "facts":
            facts = {k: v for k, v in s.items() if k not in ("step", "by")}
            console.print(f"  [cyan]1 facts (code)[/cyan] {json.dumps(facts, default=str)[:600]}", highlight=False)
        elif s["step"] == "holds_and_stops":
            console.print(f"  [cyan]3 holds/stops (code)[/cyan] {s['actions']}", highlight=False)
        elif "error" in s:
            console.print(f"  [red]2 {s['step']}: error {s['error']}[/red]", highlight=False)
        else:
            p = f"p={s['p']:.2f}" if s.get("p") is not None else s.get("reason", "")
            console.print(f"  [cyan]2 {s['step']}[/cyan] → {s['answer']}  [dim]{p}[/dim]", highlight=False)
    console.print(f"  [cyan]4 release[/cyan] → {r['verdict']}: {'; '.join(json.loads(r['reasons']))}")
