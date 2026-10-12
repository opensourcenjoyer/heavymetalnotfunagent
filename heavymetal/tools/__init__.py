"""Importing this package registers every tool."""

from heavymetal.tools import (  # noqa: F401
    analyze,
    launch,
    memory_tools,
    rpc_tools,
    scan,
    signals_tools,
    trade,
    wallet,
)
from heavymetal.tools.registry import REGISTRY, execute, schemas

__all__ = ["REGISTRY", "execute", "schemas"]
