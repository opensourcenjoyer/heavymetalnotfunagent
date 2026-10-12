"""Top status HUD widget: Displays live agent wallet, balance, cluster, and RPC node info."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label


class HeaderHUD(Widget):
    DEFAULT_CSS = """
    HeaderHUD {
        layout: horizontal;
        height: 3;
        background: #181b21;
        border-bottom: solid #2e3440;
        align-vertical: middle;
        padding: 0 1;
    }
    """

    wallet_address: reactive[str] = reactive("Loading...")
    sol_balance: reactive[float] = reactive(0.0)
    cluster: reactive[str] = reactive("mainnet")
    node_name: reactive[str] = reactive("RPC")
    latency_ms: reactive[int | None] = reactive(None)

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label("⚡ HEAVYMETAL", classes="hud-brand")
            yield Label(" | ")
            yield Label(self._format_cluster(), id="hud-cluster", classes=self._cluster_class())
            yield Label(" | ")
            yield Label(self._format_wallet(), id="hud-wallet", classes="hud-wallet")
            yield Label(" | ")
            yield Label(self._format_balance(), id="hud-balance", classes="hud-balance")
            yield Label(" | ")
            yield Label(self._format_node(), id="hud-node", classes="hud-node")

    def _format_cluster(self) -> str:
        return f"[{self.cluster.upper()}]"

    def _cluster_class(self) -> str:
        return "hud-cluster-devnet" if self.cluster == "devnet" else "hud-cluster-mainnet"

    def _format_wallet(self) -> str:
        addr = self.wallet_address
        if len(addr) > 12:
            return f"Wallet: {addr[:4]}…{addr[-4:]}"
        return f"Wallet: {addr}"

    def _format_balance(self) -> str:
        return f"SOL: {self.sol_balance:.4f}"

    def _format_node(self) -> str:
        lat = f" ({self.latency_ms}ms)" if self.latency_ms is not None else ""
        return f"Node: {self.node_name}{lat}"

    def watch_wallet_address(self, new_val: str) -> None:
        try:
            self.query_one("#hud-wallet", Label).update(self._format_wallet())
        except Exception:  # noqa: BLE001
            pass

    def watch_sol_balance(self, new_val: float) -> None:
        try:
            self.query_one("#hud-balance", Label).update(self._format_balance())
        except Exception:  # noqa: BLE001
            pass

    def watch_cluster(self, new_val: str) -> None:
        try:
            lbl = self.query_one("#hud-cluster", Label)
            lbl.update(self._format_cluster())
            lbl.classes = self._cluster_class()
        except Exception:  # noqa: BLE001
            pass

    def watch_node_name(self, new_val: str) -> None:
        try:
            self.query_one("#hud-node", Label).update(self._format_node())
        except Exception:  # noqa: BLE001
            pass

    def watch_latency_ms(self, new_val: int | None) -> None:
        try:
            self.query_one("#hud-node", Label).update(self._format_node())
        except Exception:  # noqa: BLE001
            pass
