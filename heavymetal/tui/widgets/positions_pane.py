"""Positions Sidebar Pane: Displays live tracked positions, PnL %, and manual exit buttons."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Label


class ClosePositionRequested(Message):
    """Event posted when user clicks a sell button for an open position."""

    def __init__(self, mint: str, amount_pct: str = "100%"):
        super().__init__()
        self.mint = mint
        self.amount_pct = amount_pct


class RefreshPositionsRequested(Message):
    """Event posted when user requests price refresh."""


class PositionCard(Widget):
    DEFAULT_CSS = """
    PositionCard {
        background: #1e2229;
        border: round #2e3440;
        padding: 1 1;
        margin-bottom: 1;
        height: auto;
    }
    """

    def __init__(self, pos: dict, **kwargs):
        super().__init__(**kwargs)
        self.pos = pos
        self.mint = pos.get("mint", "")
        self.symbol = pos.get("symbol", "TOKEN")

    def compose(self) -> ComposeResult:
        with Vertical():
            mint_short = f"{self.mint[:4]}…{self.mint[-4:]}" if len(self.mint) > 10 else self.mint
            pnl = self.pos.get("pnl_pct")
            pnl_str = f"{pnl:+.1f}%" if pnl is not None else "0.0%"
            pnl_cls = "pos-pnl-pos" if (pnl or 0) >= 0 else "pos-pnl-neg"

            with Horizontal():
                yield Label(f"${self.symbol} ({mint_short})", classes="hud-brand")
                yield Label(f"  {pnl_str}", classes=pnl_cls)

            entry = f"${self.pos['entry_price_usd']:.6f}" if self.pos.get("entry_price_usd") else "N/A"
            curr = f"${self.pos['current_price_usd']:.6f}" if self.pos.get("current_price_usd") else "N/A"
            yield Label(f"Entry: {entry} | Now: {curr}", classes="hud-node")

            tp = f"{self.pos.get('tp_multiple')}x" if self.pos.get("tp_multiple") else "None"
            sl = f"-{self.pos.get('sl_pct')}%" if self.pos.get("sl_pct") else "None"
            yield Label(f"Target TP: {tp} | Stop Loss: {sl}", classes="hud-node")

            trigger = self.pos.get("action_trigger", "HOLD")
            if trigger != "HOLD":
                yield Label(f"⚠ TRIGGER: {trigger}", classes="pos-pnl-neg")

            with Horizontal():
                yield Button("Sell 100%", id=f"sell-100-{self.mint}", variant="error", classes="chip-btn")
                yield Button("Sell 50%", id=f"sell-50-{self.mint}", variant="warning", classes="chip-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid.startswith("sell-100-"):
            self.post_message(ClosePositionRequested(self.mint, "100%"))
        elif bid.startswith("sell-50-"):
            self.post_message(ClosePositionRequested(self.mint, "50%"))


class PositionsPane(Widget):
    DEFAULT_CSS = """
    PositionsPane {
        width: 32%;
        height: 100%;
        background: #16191f;
        border-left: solid #2e3440;
        padding: 1 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.positions: list[dict] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal():
                yield Label("ACTIVE POSITIONS", classes="sidebar-title")
                yield Button("↻ Refresh", id="refresh-pos-btn", classes="chip-btn")
            with VerticalScroll(id="positions-scroll"):
                yield Label("[dim]No active open positions[/dim]", id="no-pos-label")

    def update_positions(self, positions: list[dict]) -> None:
        self.positions = positions
        scroll = self.query_one("#positions-scroll", VerticalScroll)
        scroll.remove_children()
        if not positions:
            scroll.mount(Label("[dim]No active open positions\n(Paste a token to audit & buy)[/dim]"))
            return
        for p in positions:
            scroll.mount(PositionCard(p))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh-pos-btn":
            self.post_message(RefreshPositionsRequested())
