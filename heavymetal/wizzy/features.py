"""Feature registry: each phase module registers its Telegram commands and router intents here."""

from __future__ import annotations

import importlib

FEATURE_MODULES: list[str] = [
    "heavymetal.wizzy.payments",
    "heavymetal.wizzy.familiars",
    "heavymetal.wizzy.tarot",
    "heavymetal.wizzy.prophecy.service",
    "heavymetal.wizzy.spellbook.surface",
]  # each exposes register()
_done = False


def register_all() -> None:
    global _done
    if _done:
        return
    for name in FEATURE_MODULES:
        mod = importlib.import_module(name)
        mod.register()
    _done = True
