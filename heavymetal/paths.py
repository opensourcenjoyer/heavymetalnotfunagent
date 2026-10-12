"""Filesystem locations. Everything lives under $HEAVYMETAL_HOME (default ~/.heavymetal)."""

import os
from pathlib import Path


def home() -> Path:
    p = Path(os.environ.get("HEAVYMETAL_HOME", Path.home() / ".heavymetal"))
    p.mkdir(parents=True, exist_ok=True)
    try:
        p.chmod(0o700)
    except OSError:
        pass
    return p


def config_path() -> Path:
    return home() / "config.toml"


def db_path() -> Path:
    return home() / "heavymetal.db"


def wallet_path() -> Path:
    return home() / "wallet.json"


def history_path() -> Path:
    return home() / "prompt_history"
