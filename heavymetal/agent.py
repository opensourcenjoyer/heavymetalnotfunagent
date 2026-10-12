"""The agent loop: LLM -> tool calls -> results -> LLM ... until the model answers without tools."""

from __future__ import annotations

import datetime as dt
import json
from importlib import resources

from heavymetal.providers.types import DeltaCallback
from heavymetal.tools import execute, schemas

KEEP_FULL = 40  # most recent messages kept verbatim
OLD_TOOL_CHARS = 400  # older tool results are clipped to this
MAX_WINDOW = 160  # messages sent at most (cut at a user turn)


def system_prompt(env) -> str:
    base = resources.files("heavymetal.prompts").joinpath("system.md").read_text()
    c = env.cfg
    header = (
        f"\n# Context\n- Agent wallet: {env.address}\n- Cluster: {env.cluster}\n"
        f"- RPC node: {c.node_name(env.rpc.url) or 'custom'} ({len(env.rpc.urls)} node(s) incl. failover)\n"
        f"- Date (UTC): {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M}\n"
        f"- Trade review: {c.review.mode} on {', '.join(c.review.actions)} "
        f"(reviewer model: {c.llm.review_model})\n"
        f"- Default slippage: {c.trade.slippage_pct}%  priority fee: {c.trade.priority_fee_sol} SOL\n"
    )
    if env.cluster != "mainnet":
        header += "- Devnet: trading, launches and market tools that need mainnet are unavailable; use airdrop.\n"
    return base + header


def sanitize(messages: list[dict]) -> list[dict]:
    """Make history valid for the API: every assistant tool_call gets a tool reply (e.g. after Ctrl+C)."""
    out: list[dict] = []
    pending: list[str] = []
    for m in messages:
        if m["role"] != "tool" and pending:
            out += [{"role": "tool", "tool_call_id": i, "content": '{"status":"interrupted"}'} for i in pending]
            pending = []
        out.append(m)
        if m["role"] == "assistant" and m.get("tool_calls"):
            pending = [tc["id"] for tc in m["tool_calls"]]
        elif m["role"] == "tool" and m.get("tool_call_id") in pending:
            pending.remove(m["tool_call_id"])
    out += [{"role": "tool", "tool_call_id": i, "content": '{"status":"interrupted"}'} for i in pending]
    return out


def build_context(env) -> list[dict]:
    msgs = sanitize(env.messages)
    if len(msgs) > MAX_WINDOW:
        start = len(msgs) - MAX_WINDOW
        while start < len(msgs) and msgs[start]["role"] != "user":
            start += 1
        msgs = msgs[start:]
    cut = len(msgs) - KEEP_FULL
    ctx = []
    for i, m in enumerate(msgs):
        if i < cut and m["role"] == "tool" and len(m.get("content") or "") > OLD_TOOL_CHARS:
            m = {**m, "content": m["content"][:OLD_TOOL_CHARS] + ' …"[older result clipped]"'}
        ctx.append(m)
    return [{"role": "system", "content": system_prompt(env)}] + ctx


def _add(env, msg: dict) -> None:
    env.messages.append(msg)
    env.db.add_message(env.session_id, msg)


async def run_turn(env, user_text: str, on_delta: DeltaCallback | None = None) -> str:
    _add(env, {"role": "user", "content": user_text})
    tools = schemas(env.cluster)
    for _ in range(env.cfg.llm.max_iterations):
        resp = await env.agent_llm.complete(build_context(env), tools, on_delta)
        env.db.add_usage(
            env.session_id, "agent", env.agent_llm.model, resp.input_tokens, resp.output_tokens, resp.cost_usd
        )
        msg: dict = {"role": "assistant", "content": resp.content or ""}
        if resp.tool_calls:
            msg["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in resp.tool_calls
            ]
        _add(env, msg)
        if not resp.tool_calls:
            return resp.content
        for tc in resp.tool_calls:
            env.emit("tool_start", {"name": tc.name, "arguments": tc.arguments})
            result = await execute(env, tc.name, tc.arguments)
            env.emit("tool_end", {"name": tc.name, "result": result})
            _add(env, {"role": "tool", "tool_call_id": tc.id, "content": result})
    note = f"[stopped: reached max_iterations ({env.cfg.llm.max_iterations})]"
    _add(env, {"role": "assistant", "content": note})
    return note


def short(result_json: str, n: int = 160) -> str:
    try:
        d = json.loads(result_json)
    except json.JSONDecodeError:
        return result_json[:n]
    status = d.get("status", "?")
    if status == "blocked":
        return f"blocked: {d.get('verdict')} - {'; '.join(d.get('reasons', []))}"[:n]
    if status == "error":
        return f"error: {d.get('reason')}"[:n]
    keys = [k for k in d if k not in ("status", "note")][:5]
    return (f"{status}: " + ", ".join(keys))[:n]
