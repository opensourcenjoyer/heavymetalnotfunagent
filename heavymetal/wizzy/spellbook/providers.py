"""Unlock schedule providers. None of heavymetal's sources carry vesting data, so the default says so plainly."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Unlock:
    mint: str
    ts: float
    amount: float
    pct_supply: float | None = None
    label: str = ""


class UnlockProvider:
    name = "base"
    available = False

    async def upcoming(self, mint: str, within_days: int = 14) -> list[Unlock]:
        raise NotImplementedError


class NullUnlockProvider(UnlockProvider):
    name = "none"
    available = False
    message = "The mists hide unlock schedules for now: no vesting data source is connected yet."

    async def upcoming(self, mint: str, within_days: int = 14) -> list[Unlock]:
        return []


PROVIDER: UnlockProvider = NullUnlockProvider()
