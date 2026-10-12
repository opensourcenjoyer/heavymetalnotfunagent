"""Main Textual Fullscreen Application: HeavyMetalApp."""

from __future__ import annotations

import json

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer

from heavymetal.agent import run_turn
from heavymetal.env import AgentEnv
from heavymetal.solana.positions import evaluate_open_positions
from heavymetal.tui.widgets import (
    ChatStream,
    ClosePositionRequested,
    HeaderHUD,
    InputBar,
    PositionsPane,
    QuickBuyRequested,
    RefreshPositionsRequested,
    UserMessageSubmitted,
)


class HeavyMetalApp(App):
    CSS_PATH = "styles.tcss"
    TITLE = "Heavy Metal Agent"
    SUB_TITLE = "Solana Memecoin Terminal"

    def __init__(self, env: AgentEnv, **kwargs):
        super().__init__(**kwargs)
        self.env = env
        self._is_running_turn = False

    def compose(self) -> ComposeResult:
        yield HeaderHUD(id="header-hud")
        with Horizontal(id="main-container"):
            yield ChatStream(id="chat-container")
            yield PositionsPane(id="positions-sidebar")
        yield InputBar(id="input-bar")
        yield Footer()

    async def on_mount(self) -> None:
        hud = self.query_one(HeaderHUD)
        hud.wallet_address = self.env.address
        hud.cluster = self.env.cluster
        hud.node_name = self.env.cfg.node_name() or "RPC"

        # Check for configured LLM key
        if not (self.env.cfg.llm.api_key or self.env.cfg.llm.anthropic_key):
            chat = self.query_one(ChatStream)
            chat.add_agent_message(
                "⚠️ **No LLM API Key detected.**\n\n"
                "Please configure an **Anthropic** key (`sk-ant-...`) or **OpenRouter** key (`sk-or-...`) "
                "in `~/.heavymetal/config.toml` or export `ANTHROPIC_API_KEY`."
            )

        # Autofocus the input box so the user can immediately type
        try:
            from textual.widgets import Input

            self.query_one("#prompt-input", Input).focus()
        except Exception:  # noqa: BLE001
            pass

        # Wire agent event hook
        orig_emit = getattr(self.env, "on_event", None)

        def tui_event_handler(kind: str, payload: dict):
            if callable(orig_emit):
                orig_emit(kind, payload)
            self._handle_agent_event(kind, payload)

        self.env.on_event = tui_event_handler

        # Initial background data fetch
        self.refresh_wallet_status()
        self.refresh_positions_worker()

        # Periodic background tasks
        self.set_interval(6.0, self.refresh_positions_worker)
        self.set_interval(15.0, self.refresh_wallet_status)

    def _run_on_app(self, fn, *args) -> None:
        import threading

        if threading.get_ident() == getattr(self, "_thread_id", None):
            fn(*args)
        else:
            self.call_from_thread(fn, *args)

    def _handle_agent_event(self, kind: str, p: dict) -> None:
        chat = self.query_one(ChatStream)
        if kind == "tool_end":
            name = p.get("name", "")
            raw_res = p.get("result", "{}")
            try:
                data = json.loads(raw_res) if isinstance(raw_res, str) else raw_res
            except Exception:  # noqa: BLE001
                data = {}

            if name in ("token_audit", "degen_audit") and data.get("status") == "success":
                self._run_on_app(chat.add_radar_card, data)
            elif name in ("swap", "pump_trade", "buy_with_tpsl") and data.get("status") == "success":
                trade_info = data.get("swap") if name == "buy_with_tpsl" else data
                if isinstance(trade_info, dict):
                    pos_info = data.get("position")
                    payload = {**trade_info, "position": pos_info}
                    self._run_on_app(chat.add_trade_card, payload)
                    self._run_on_app(self.refresh_positions_worker)
                    self._run_on_app(self.refresh_wallet_status)

        elif kind == "review":
            verdict = p.get("verdict", "")
            if verdict not in ("EXECUTE", "REDUCE_SIZE"):
                self.notify(f"Review Gate Hold: {verdict}", severity="warning")

    @work(exclusive=True)
    async def refresh_wallet_status(self) -> None:
        hud = self.query_one(HeaderHUD)
        try:
            bal = await self.env.rpc.balance_sol(self.env.address)
            hud.sol_balance = bal
        except Exception:  # noqa: BLE001
            pass

    @work(exclusive=True)
    async def refresh_positions_worker(self) -> None:
        sidebar = self.query_one(PositionsPane)
        try:
            positions = await evaluate_open_positions(self.env)
            sidebar.update_positions(positions)
            for p in positions:
                trig = p.get("action_trigger")
                if trig == "TRIGGER_TP":
                    self.notify(f"🎯 Take-Profit Target Hit for ${p.get('symbol')}!", severity="information")
                elif trig == "TRIGGER_SL":
                    self.notify(f"⚠ Stop-Loss Trigger Hit for ${p.get('symbol')}!", severity="error")
        except Exception:  # noqa: BLE001
            pass

    def on_user_message_submitted(self, event: UserMessageSubmitted) -> None:
        text = event.text.strip()
        if not text:
            return

        chat = self.query_one(ChatStream)
        chat.add_user_message(text)

        # Handle local slash shortcuts
        if text == "/wallet":
            self.refresh_wallet_status()
            bal = self.query_one(HeaderHUD).sol_balance
            chat.add_agent_message(f"**Agent Native Wallet:** `{self.env.address}`\n\n**SOL Balance:** {bal:.4f} SOL")
            return
        if text == "/positions":
            self.refresh_positions_worker()
            chat.add_agent_message("Refreshed active positions pane.")
            return
        if text == "/new":
            self.env.session_id = self.env.db.new_session()
            self.env.messages.clear()
            self.env.research.clear()
            chat.add_agent_message("Started fresh chat session.")
            return

        # Run turn with agent
        self.run_agent_turn(text)

    def on_quick_buy_requested(self, event: QuickBuyRequested) -> None:
        cmd = f"buy {event.sol_amount} SOL of {event.mint} with 2x TP, 30% SL"
        chat = self.query_one(ChatStream)
        chat.add_user_message(cmd)
        self.run_agent_turn(cmd)

    def on_close_position_requested(self, event: ClosePositionRequested) -> None:
        cmd = f"sell {event.amount_pct} of {event.mint}"
        chat = self.query_one(ChatStream)
        chat.add_user_message(cmd)
        self.run_agent_turn(cmd)

    def on_refresh_positions_requested(self, event: RefreshPositionsRequested) -> None:
        self.refresh_positions_worker()
        self.notify("Refreshed position market prices", severity="information")

    @work(exclusive=False)
    async def run_agent_turn(self, user_text: str) -> None:
        if self._is_running_turn:
            self.notify("Agent is already running a task...", severity="warning")
            return

        self._is_running_turn = True
        chat = self.query_one(ChatStream)
        chat.set_thinking("evaluating...")

        def on_delta(kind: str, text: str):
            if kind == "reasoning":
                self._run_on_app(chat.set_thinking, text[:100].replace("\n", " "))

        try:
            reply = await run_turn(self.env, user_text, on_delta=on_delta)
            chat.set_thinking(None)
            if reply:
                chat.add_agent_message(reply)
        except Exception as e:  # noqa: BLE001
            chat.set_thinking(None)
            chat.add_agent_message(f"**Error:** {e}")
        finally:
            self._is_running_turn = False
            self.refresh_wallet_status()
            self.refresh_positions_worker()
