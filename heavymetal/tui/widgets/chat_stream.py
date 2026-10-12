"""Scrollable chat stream widget: Handles styled user & agent message bubbles, radar cards, and trade cards."""

from __future__ import annotations

import datetime as dt

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Label, Markdown

from heavymetal.tui.widgets.radar_card import RadarCard
from heavymetal.tui.widgets.trade_card import TradeCard


class UserMessageWidget(Widget):
    DEFAULT_CSS = """
    UserMessageWidget {
        background: #1e222b;
        border-left: thick #9945ff;
        padding: 1 1;
        margin-bottom: 1;
        height: auto;
    }
    """

    def __init__(self, text: str, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.time_str = dt.datetime.now().strftime("%H:%M")

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"👤 You  [dim]{self.time_str}[/dim]", classes="chat-sender-user")
            yield Label(self.text)


class AgentMessageWidget(Widget):
    DEFAULT_CSS = """
    AgentMessageWidget {
        background: #181c22;
        border-left: thick #14f195;
        padding: 1 1;
        margin-bottom: 1;
        height: auto;
    }
    """

    def __init__(self, text: str, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.time_str = dt.datetime.now().strftime("%H:%M")

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"⚡ Heavy Metal Agent  [dim]{self.time_str}[/dim]", classes="chat-sender-agent")
            yield Markdown(self.text)


class ChatStream(Widget):
    DEFAULT_CSS = """
    ChatStream {
        width: 70%;
        height: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="chat-scroll"):
            welcome = (
                "**Ready to trade Solana memecoins.**\n\n"
                "• Paste any **DexScreener** link, pump.fun URL, or token contract address for an instant audit.\n"
                "• Execute buys with automatic Take-Profit and Stop-Loss (e.g. `buy 0.05 SOL with 2x TP, 30% SL`).\n"
                "• Use `/wallet` to view balances, `/positions` for live PnL, or `/rpc` to benchmark nodes."
            )
            yield AgentMessageWidget(welcome)

    def scroll_bottom(self) -> None:
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        scroll.scroll_end(animate=False)

    def add_user_message(self, text: str) -> None:
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        scroll.mount(UserMessageWidget(text))
        self.scroll_bottom()

    def add_agent_message(self, text: str) -> None:
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        scroll.mount(AgentMessageWidget(text))
        self.scroll_bottom()

    def add_radar_card(self, data: dict) -> None:
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        scroll.mount(RadarCard(data))
        self.scroll_bottom()

    def add_trade_card(self, data: dict) -> None:
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        scroll.mount(TradeCard(data))
        self.scroll_bottom()

    def set_thinking(self, text: str | None) -> None:
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        for child in scroll.query(".chat-thinking"):
            child.remove()
        if text:
            scroll.mount(Label(f"⠋ {text}", classes="chat-thinking"))
            self.scroll_bottom()
