"""Trade Execution Card: Renders executed swaps, fills, signatures, and target TP/SL bounds."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label


class TradeCard(Widget):
    DEFAULT_CSS = """
    TradeCard {
        background: #17211b;
        border: solid #14f195;
        padding: 1 2;
        margin: 1 0;
        height: auto;
    }
    """

    def __init__(self, data: dict, **kwargs):
        super().__init__(**kwargs)
        self.data = data
        self.action = data.get("action") or data.get("side", "TRADE")
        self.mint = data.get("mint", "")
        self.symbol = data.get("symbol", "TOKEN")
        self.sol_amount = data.get("amount") or data.get("sol_amount") or 0.0
        self.sig = data.get("signature") or ""
        self.position = data.get("position", {})

    def compose(self) -> ComposeResult:
        with Vertical():
            mint_short = f"{self.mint[:6]}…{self.mint[-4:]}" if len(self.mint) > 12 else self.mint
            header = f"🚀 EXECUTED {self.action.upper()}: ${self.symbol} ({mint_short})"
            yield Label(header, classes="trade-header")

            details = f"Amount: {self.sol_amount} SOL | Venue: {self.data.get('venue', 'Solana')}"
            yield Label(details)

            if self.position:
                tp = f"{self.position.get('tp_multiple')}x" if self.position.get("tp_multiple") else "None"
                sl = f"-{self.position.get('sl_pct')}%" if self.position.get("sl_pct") else "None"
                targets = f"Targets: TP: {tp} | SL: {sl} (Registered in local position manager)"
                yield Label(targets, classes="pos-pnl-pos")

            if self.sig:
                explorer = f"https://solscan.io/tx/{self.sig}"
                yield Label(f"Explorer: {explorer}")
