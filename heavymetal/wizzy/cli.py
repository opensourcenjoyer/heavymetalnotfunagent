"""Terminal output for `wizzy read`: the bear waits (animated) while the runes are read."""

from __future__ import annotations

import contextlib

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from heavymetal import mascot

console = Console()


class _Waiting:
    def __init__(self, label: str):
        self.label = label

    def __rich__(self):
        import time

        dots = "." * (int(time.monotonic() * 2) % 4)
        return mascot.beside(mascot.waiting(), Text(f"{self.label}{dots}", style="magenta"))


@contextlib.contextmanager
def waiting(label: str = "reading the runes"):
    if not mascot.enabled(console):
        with console.status(label):
            yield
        return
    live = Live(_Waiting(label), console=console, refresh_per_second=mascot.FPS, transient=True)
    live.start()
    try:
        yield
    finally:
        live.stop()


OMEN_STYLE = {"cursed": "red", "hexed": "magenta", "murky": "yellow", "blessed": "green", None: "cyan"}


def show_reading(r) -> None:
    style = OMEN_STYLE.get(r.omen, "cyan")
    console.print(Panel(Text(r.written.reading), title=f"[bold]{r.written.title}[/bold]", border_style=style))
    console.print(Markdown(r.written.body))
    note = "templated (no model)" if r.written.templated else f"{r.written.model} · ${r.written.cost_usd:.4f}"
    if r.cached:
        note = "reused a recent scroll"
    console.print(f"[dim]scroll {r.url} · {note}[/dim]")
    if r.written.problems:
        console.print(f"[dim]guard rejected the model draft: {'; '.join(r.written.problems[:3])}[/dim]")


def show_scroll(s, url: str, cached: bool = False) -> None:
    console.print(Panel(Text(s.reading), title=f"[bold]{s.title}[/bold]", border_style=OMEN_STYLE.get(s.omen, "cyan")))
    console.print(Markdown(s.body_md))
    console.print(f"[dim]scroll {url}{' · reused a recent scroll' if cached else ''}[/dim]")
