"""Long-term memory and the trade ledger, exposed to the agent."""

from __future__ import annotations

from heavymetal.tools.registry import ok, tool


@tool(
    "remember",
    "Store a durable note (strategy, a token to watch, a wallet to track) for future sessions.",
    {"content": {"type": "string"}, "tags": {"type": "string"}},
    ["content"],
)
async def remember(env, content: str, tags: str = ""):
    return ok(id=env.db.remember(content, tags))


@tool("recall", "Search stored notes.", {"query": {"type": "string"}}, ["query"])
async def recall(env, query: str):
    return ok(results=env.db.recall(query))


@tool(
    "trade_history",
    "The agent's own ledger of signed transactions (sends, buys, sells, launches).",
    {"limit": {"type": "integer", "default": 15}, "mint": {"type": "string"}},
)
async def trade_history(env, limit: int = 15, mint: str | None = None):
    rows = env.db.trades(min(limit, 100), mint)
    return ok(
        trades=[
            {
                k: r[k]
                for k in (
                    "ts",
                    "tool",
                    "action",
                    "mint",
                    "amount",
                    "unit",
                    "counterparty",
                    "signature",
                    "status",
                    "error",
                )
            }
            for r in rows
        ]
    )
