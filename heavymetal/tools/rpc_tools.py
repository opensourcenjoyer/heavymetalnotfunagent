"""Agent-facing RPC tools. Switching is limited to nodes the user saved: the agent can never point the
wallet at a URL it read somewhere (a malicious node could fake balances, prices or blockhashes)."""

from __future__ import annotations

from heavymetal.solana import nodes
from heavymetal.tools.registry import err, ok, tool


@tool("rpc_status", "List the saved Solana RPC nodes with latency, slot and cluster, and which one is active.")
async def rpc_status(env):
    return ok(fallback=env.cfg.solana.rpc_fallback, nodes=await nodes.status(env))


@tool(
    "switch_rpc",
    "Switch the active RPC node to one of the user's SAVED nodes (by name, see rpc_status). "
    "Only do this when the user asks, or after repeated RPC failures. Arbitrary URLs are not accepted.",
    {"name": {"type": "string", "description": "saved node name"}},
    ["name"],
)
async def switch_rpc(env, name: str):
    if name not in env.cfg.solana.rpc_nodes:
        return err(
            f"'{name}' is not a saved node. Saved: {', '.join(env.cfg.solana.rpc_nodes)}. "
            "The user can add nodes with /rpc add <name> <url>."
        )
    try:
        res = await nodes.use(env, name)
    except nodes.NodeError as e:
        return err(str(e))
    return ok(**res)
