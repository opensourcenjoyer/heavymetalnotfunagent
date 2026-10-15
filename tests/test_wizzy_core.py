import time

import tomli_w

from heavymetal import config as config_mod
from heavymetal.config import Config
from heavymetal.data import connectors
from heavymetal.env import mainnet_config
from heavymetal.wizzy.db import WizzyDB


def test_wizzy_config_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("HEAVYMETAL_HOME", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    (tmp_path / "config.toml").write_text(tomli_w.dumps({"wizzy": {"free_readings_per_hour": 7, "x_enabled": True}}))
    cfg = config_mod.load()
    assert cfg.wizzy.free_readings_per_hour == 7
    assert cfg.wizzy.x_enabled is True
    assert cfg.keys.telegram_bot_token == "123:abc"


def test_wizzy_keys_do_not_show_as_missing_data_sources():
    cfg = Config()
    assert "telegram_bot_token" not in connectors.missing(cfg)
    assert "telegram_bot_token" in connectors.missing(cfg, "wizzy")
    assert "telegram_bot_token" in connectors.KEYED  # still settable with /keys set


def test_mainnet_config_ignores_devnet_active_node():
    cfg = Config()
    cfg.solana.rpc_url = "https://api.devnet.solana.com"
    cfg.solana.cluster = "devnet"
    m = mainnet_config(cfg)
    assert m.solana.cluster == "mainnet"
    assert "devnet" not in m.solana.rpc_url
    assert cfg.solana.cluster == "devnet"  # original untouched


def test_wizzy_db_schema_users_and_secrets(tmp_path):
    db = WizzyDB(tmp_path / "w.db")
    assert db.meta("schema_version") == "1"
    u = db.user(tg_id="42")
    assert db.user(tg_id="42")["id"] == u["id"]
    assert db.tier(u["id"]) == "free"
    db._x("UPDATE users SET tier='inner', tier_expires_at=? WHERE id=?", (time.time() + 60, u["id"]))
    assert db.tier(u["id"]) == "inner"
    db._x("UPDATE users SET tier_expires_at=? WHERE id=?", (time.time() - 1, u["id"]))
    assert db.tier(u["id"]) == "free"
    s1 = db.secret("cookie")
    assert s1 == WizzyDB(tmp_path / "w.db").secret("cookie")
    sid = db.subject("token", "MINT1", "ABC")
    assert db.subject("token", "MINT1") == sid


def test_wizzy_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("HEAVYMETAL_HOME", str(tmp_path))
    monkeypatch.setenv("WIZZY_BASE_URL", "https://wizzy.example")
    monkeypatch.setenv("WIZZY_X_ENABLED", "true")
    monkeypatch.setenv("WIZZY_PORT", "9000")
    monkeypatch.setenv("WIZZY_PROPHECY_HOURS_UTC", "8,20")
    monkeypatch.setenv("WIZZY_DAILY_LLM_BUDGET_USD", "2.5")
    w = config_mod.load().wizzy
    assert (w.base_url, w.x_enabled, w.port, w.prophecy_hours_utc, w.daily_llm_budget_usd) == (
        "https://wizzy.example",
        True,
        9000,
        [8, 20],
        2.5,
    )
