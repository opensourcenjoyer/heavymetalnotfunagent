import pytest

from heavymetal.tui.widgets.header_hud import HeaderHUD
from heavymetal.tui.widgets.positions_pane import PositionCard
from heavymetal.tui.widgets.radar_card import RadarCard, make_ascii_bar
from heavymetal.tui.widgets.trade_card import TradeCard


def test_make_ascii_bar():
    assert make_ascii_bar(None) == "[----------------]"
    assert make_ascii_bar(1.0, width=10) == "[██████████]"
    assert make_ascii_bar(0.0, width=10) == "[░░░░░░░░░░]"
    assert make_ascii_bar(0.5, width=10) == "[█████░░░░░]"


def test_header_hud_formatters():
    hud = HeaderHUD()
    hud.wallet_address = "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"
    hud.sol_balance = 0.5432
    hud.cluster = "mainnet"
    hud.node_name = "QuickNode"
    hud.latency_ms = 25

    assert "4k3D…kX6R" in hud._format_wallet()
    assert "0.5432" in hud._format_balance()
    assert "MAINNET" in hud._format_cluster()
    assert "QuickNode (25ms)" in hud._format_node()


def test_radar_card_instantiation():
    data = {
        "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        "verdict": "HIGH CONVICTION (BULLISH)",
        "reasons": ["Clean contract", "Strong volume"],
        "market": {
            "symbol": "BONK",
            "price_usd": 0.000025,
            "liquidity_usd": 500_000,
            "fdv": 1_000_000_000,
            "buy_ratio_h1": 0.85,
            "buys_h1": 150,
            "sells_h1": 25,
        },
        "safety": {
            "mint_authority": None,
            "freeze_authority": None,
            "lp_locked_pct": 100,
        },
        "holders": {
            "top10_pct": 18.5,
        },
        "bubblemaps_url": "https://app.bubblemaps.io/sol/token/DezX...",
    }
    card = RadarCard(data)
    assert card.symbol == "BONK"
    assert card.verdict == "HIGH CONVICTION (BULLISH)"


def test_trade_card_instantiation():
    trade_data = {
        "action": "buy",
        "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        "symbol": "BONK",
        "amount": 0.05,
        "signature": "5x9Abc123...",
        "position": {
            "tp_multiple": 2.0,
            "sl_pct": 30.0,
        },
    }
    card = TradeCard(trade_data)
    assert card.action == "buy"
    assert card.symbol == "BONK"
    assert card.sol_amount == 0.05


def test_position_card_instantiation():
    pos = {
        "id": 1,
        "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        "symbol": "BONK",
        "entry_price_usd": 0.00002,
        "current_price_usd": 0.00003,
        "pnl_pct": 50.0,
        "tp_multiple": 2.0,
        "sl_pct": 30.0,
        "action_trigger": "HOLD",
    }
    card = PositionCard(pos)
    assert card.symbol == "BONK"
    assert card.pos["pnl_pct"] == 50.0


@pytest.mark.anyio
async def test_app_mount(make_env):
    from heavymetal.tui.app import HeavyMetalApp

    env = make_env()
    # Mock open_positions
    env.db.open_positions = lambda mint=None: []
    app = HeavyMetalApp(env)
    async with app.run_test():
        assert app.is_mounted
        assert app.query_one("#header-hud") is not None
        assert app.query_one("#chat-container") is not None
        assert app.query_one("#positions-sidebar") is not None
        assert app.query_one("#prompt-input") is not None


def test_web_mode_launches_tui_flag(monkeypatch):
    """`heavymetal --web` must spawn the TUI with a command main.py's argparse accepts."""
    import shlex

    from heavymetal.tui import web

    captured = {}

    class FakeServer:
        def __init__(self, command, **kw):
            captured["command"] = command

        def serve(self):
            pass

    monkeypatch.setattr(web, "Server", FakeServer)
    web.run_web()
    argv = shlex.split(captured["command"])
    assert argv[1:] == ["-m", "heavymetal.main", "--tui"]
