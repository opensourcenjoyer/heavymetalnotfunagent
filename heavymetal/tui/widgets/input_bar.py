"""Bottom Input Bar Widget: Action chips, text input, and auto-paste link interceptor."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input


class UserMessageSubmitted(Message):
    """Event posted when user submits a message or clicks a command chip."""

    def __init__(self, text: str):
        super().__init__()
        self.text = text


class InputBar(Widget):
    DEFAULT_CSS = """
    InputBar {
        dock: bottom;
        height: 6;
        background: #181b21;
        border-top: solid #2e3440;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="chips-row"):
            yield Button("Trending", id="chip-trending", classes="chip-btn")
            yield Button("Holdings", id="chip-wallet", classes="chip-btn")
            yield Button("Positions", id="chip-positions", classes="chip-btn")
            yield Button("Nodes", id="chip-rpc", classes="chip-btn")
            yield Button("Clear Chat", id="chip-clear", classes="chip-btn")
        with Horizontal(id="input-row"):
            yield Input(placeholder="Type message or paste DexScreener link...", id="prompt-input")
            yield Button("SEND", id="send-button")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "send-button":
            self._submit()
        elif bid == "chip-trending":
            self.post_message(UserMessageSubmitted("show trending tokens right now"))
        elif bid == "chip-wallet":
            self.post_message(UserMessageSubmitted("/wallet"))
        elif bid == "chip-positions":
            self.post_message(UserMessageSubmitted("/positions"))
        elif bid == "chip-rpc":
            self.post_message(UserMessageSubmitted("/rpc"))
        elif bid == "chip-clear":
            self.post_message(UserMessageSubmitted("/new"))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        inp = self.query_one("#prompt-input", Input)
        text = inp.value.strip()
        if not text:
            return
        inp.value = ""

        # Auto-detect raw DexScreener or pump.fun link without command
        if text.startswith(
            ("https://dexscreener.com/", "http://dexscreener.com/", "https://pump.fun/", "http://pump.fun/")
        ):
            text = f"audit {text}"

        self.post_message(UserMessageSubmitted(text))
