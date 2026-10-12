"""Importing this package registers every tool."""

from heavymetal.tools import analyze, launch, memory_tools, rpc_tools, scan, trade, wallet  # noqa: F401
from heavymetal.tools.registry import REGISTRY, execute, schemas

__all__ = ["REGISTRY", "execute", "schemas"]
