"""Token Radar Card: Parses and renders market data, buy/sell ratios, contract security, and verdict."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Label


def make_ascii_bar(ratio: float | None, width: int = 16) -> str:
    """Generate a clean ASCII progress bar for buy/sell ratio."""
    if ratio is None or ratio < 0:
        return "[----------------]"
    fill = round(ratio * width)
    fill = max(0, min(width, fill))
    bar = "█" * fill + "░" * (width - fill)
    return f"[{bar}]"


class QuickBuyRequested(Message):
    """Event posted when user clicks a quick-buy button on the radar card."""

    def __init__(self, mint: str, sol_amount: float, symbol: str):
        super().__init__()
        self.mint = mint
        self.sol_amount = sol_amount
        self.symbol = symbol


class RadarCard(Widget):
    DEFAULT_CSS = """
    RadarCard {
        background: #1c2027;
        border: solid #9945ff;
        padding: 1 2;
        margin: 1 0;
        height: auto;
    }
    """

    def __init__(self, data: dict, **kwargs):
        super().__init__(**kwargs)
        self.data = data
        self.mint = data.get("mint", "")
        self.market = data.get("market", {})
        self.safety = data.get("safety", {})
        self.holders = data.get("holders", {})
        self.verdict = data.get("verdict", "UNKNOWN")
        self.reasons = data.get("reasons", [])
        self.symbol = self.market.get("symbol") or "TOKEN"

    def compose(self) -> ComposeResult:
        with Vertical():
            # 1. Header Row
            venue = self.market.get("dex") or "Solana"
            mint_short = f"{self.mint[:6]}…{self.mint[-4:]}" if len(self.mint) > 12 else self.mint
            header_text = f"🎯 ${self.symbol} ({mint_short})  ───  Venue: {venue.upper()}"
            yield Label(header_text, classes="radar-header")

            # 2. Market Metrics Row
            price = f"${self.market['price_usd']:.6f}" if self.market.get("price_usd") else "N/A"
            liq = f"${self.market['liquidity_usd']:,.0f}" if self.market.get("liquidity_usd") else "N/A"
            fdv = f"${self.market['fdv']:,.0f}" if self.market.get("fdv") else "N/A"
            age = f"{self.market['age_hours']}h" if self.market.get("age_hours") is not None else "Fresh"
            vol_1h = f"${self.market['volume_h1']:,.0f}" if self.market.get("volume_h1") else "N/A"
            chg_1h = (
                f"{self.market['price_change_h1']:+.1f}%" if self.market.get("price_change_h1") is not None else "0%"
            )

            metrics_line = f"Price: {price} | Liq: {liq} | MC/FDV: {fdv} | Age: {age} | 1h Vol: {vol_1h} ({chg_1h})"
            yield Label(metrics_line, classes="radar-metrics")

            # 3. Buy/Sell Momentum Bar
            buy_ratio = self.market.get("buy_ratio_h1")
            buys = self.market.get("buys_h1", 0)
            sells = self.market.get("sells_h1", 0)
            bar_visual = make_ascii_bar(buy_ratio)
            pct_text = f"{int(buy_ratio * 100)}% Buys" if buy_ratio is not None else "N/A"
            bar_line = f"Buy/Sell Pressure: {bar_visual} {pct_text} ({buys} buys / {sells} sells)"
            yield Label(bar_line, classes="radar-bar")

            # 4. Safety & Security Grid
            freeze_ok = "✓ REVOKED" if not self.safety.get("freeze_authority") else "✗ ACTIVE"
            mint_ok = "✓ REVOKED" if not self.safety.get("mint_authority") else "⚠ ACTIVE"
            lp_pct = self.safety.get("lp_locked_pct")
            lp_str = f"✓ {lp_pct}%" if lp_pct else "⚠ UNLOCKED"
            top10 = f"{self.holders.get('top10_pct')}%" if self.holders.get("top10_pct") is not None else "N/A"
            t2022_str = (
                f"⚠ TAX {self.safety.get('transfer_fee_bps', 0) / 100}%"
                if self.safety.get("transfer_fee_bps", 0) > 0
                else "✓ CLEAN"
            )

            safety_line_1 = f"Security: Mint: [{mint_ok}] | Freeze: [{freeze_ok}] | LP Locked: [{lp_str}]"
            safety_line_2 = f"Distribution: Top 10 hold {top10} | Token-2022: [{t2022_str}]"
            yield Label(safety_line_1, classes="radar-safety")
            yield Label(safety_line_2, classes="radar-safety")

            # Bubblemaps Link
            bubble_url = self.data.get("bubblemaps_url") or f"https://app.bubblemaps.io/sol/token/{self.mint}"
            yield Label(f"Bubblemaps: {bubble_url}", classes="radar-safety")

            # 5. Verdict Banner
            verdict_class = "verdict-speculative"
            if "BULLISH" in self.verdict or "APE" in self.verdict:
                verdict_class = "verdict-bullish"
            elif "PASS" in self.verdict or "FAKE" in self.verdict or "RISK" in self.verdict:
                verdict_class = "verdict-avoid"

            verdict_text = f"⚡ VERDICT: [{self.verdict}]"
            yield Label(verdict_text, classes=verdict_class)

            # Bullet reasons
            for r in self.reasons[:3]:
                yield Label(f" • {r}")

            # 6. Interactive Quick-Action Buttons
            with Horizontal(classes="radar-actions"):
                yield Button("Buy 0.05 SOL", id=f"buy-005-{self.mint}", variant="success")
                yield Button("Buy 0.1 SOL", id=f"buy-010-{self.mint}", variant="primary")
                yield Button("Copy Mint", id=f"copy-{self.mint}", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("buy-005-"):
            self.post_message(QuickBuyRequested(self.mint, 0.05, self.symbol))
        elif button_id.startswith("buy-010-"):
            self.post_message(QuickBuyRequested(self.mint, 0.10, self.symbol))
        elif button_id.startswith("copy-"):
            # Copy to clipboard if available
            try:
                self.app.copy_to_clipboard(self.mint)
                self.notify(f"Copied mint: {self.mint[:8]}…", severity="information")
            except Exception:  # noqa: BLE001
                self.notify(f"Mint: {self.mint}", severity="information")
