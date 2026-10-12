"""RPC node management: probe, switch, add, remove. Shared by the /rpc command and the agent tools.

Every node is tagged with its cluster, detected from the genesis hash, so failover never mixes
mainnet and devnet (a devnet node would report wrong balances and blockhashes for mainnet).
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlsplit

import httpx

from heavymetal import config as config_mod

GENESIS = {
    "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d": "mainnet",
    "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG": "devnet",
    "4uhcVJyU9pJkvQyS88uRDiswHXSCkY3zQawwpjk2NmaY": "testnet",
}


class NodeError(ValueError):
    pass


def mask_url(url: str) -> str:
    """Hide API keys: QuickNode/Helius/etc put them in the path or query."""
    p = urlsplit(url)
    if not p.scheme:
        return url
    secret = len(p.path.strip("/")) > 0 or bool(p.query)
    return f"{p.scheme}://{p.netloc}{'/…' if secret else ''}"


async def _rpc(http: httpx.AsyncClient, url: str, method: str, timeout: float):
    r = await http.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(str(data["error"].get("message", data["error"])))
    return data["result"]


async def probe(http: httpx.AsyncClient, url: str, timeout: float = 6.0) -> dict:
    """{ok, cluster, slot, latency_ms, error}. Latency is a getSlot round trip."""
    if urlsplit(url).scheme not in ("http", "https"):
        return {"ok": False, "error": "URL must start with http:// or https://"}
    try:
        genesis = await _rpc(http, url, "getGenesisHash", timeout)
        t0 = time.monotonic()
        slot = await _rpc(http, url, "getSlot", timeout)
        latency = round((time.monotonic() - t0) * 1000)
    except Exception as e:  # noqa: BLE001
        msg = str(e) or type(e).__name__
        return {"ok": False, "error": msg.replace(url, mask_url(url))[:200]}
    return {"ok": True, "cluster": GENESIS.get(genesis, "localnet"), "slot": slot, "latency_ms": latency}


def _apply(env, persist: bool = True) -> None:
    env.rpc.set_urls(env.cfg.rpc_urls())
    if persist:
        config_mod.save(env.cfg)


def resolve(cfg, target: str) -> tuple[str | None, str]:
    """name or URL -> (saved name or None, url)."""
    nodes = cfg.solana.rpc_nodes
    if target in nodes:
        return target, nodes[target]["url"]
    if target.startswith(("http://", "https://")):
        return cfg.node_name(target), target
    raise NodeError(f"unknown node '{target}'. Saved: {', '.join(nodes)}")


async def status(env) -> list[dict]:
    cfg = env.cfg
    names = list(cfg.solana.rpc_nodes)
    results = await asyncio.gather(*(probe(env.http, cfg.solana.rpc_nodes[n]["url"]) for n in names))
    serving = env.rpc.url
    rows = []
    for n, r in zip(names, results, strict=True):
        node = cfg.solana.rpc_nodes[n]
        rows.append(
            {
                "name": n,
                "url": mask_url(node["url"]),
                "cluster": node["cluster"],
                "active": node["url"] == cfg.solana.rpc_url,
                "serving": node["url"] == serving,
                "fallback": node["url"] in env.rpc.urls[1:],
                **r,
            }
        )
    return rows


async def add(env, name: str, url: str) -> dict:
    nodes = env.cfg.solana.rpc_nodes
    if not name.replace("-", "").replace("_", "").isalnum():
        raise NodeError("name: letters, digits, - and _ only")
    if name in nodes:
        raise NodeError(f"'{name}' already exists; remove it first")
    p = await probe(env.http, url)
    if not p["ok"]:
        raise NodeError(f"node did not respond: {p['error']}")
    nodes[name] = {"url": url, "cluster": p["cluster"]}
    _apply(env)
    return {"name": name, "url": mask_url(url), **p}


async def use(env, target: str, persist: bool = True) -> dict:
    """Switch the active node (saved name, or a URL that gets saved automatically)."""
    cfg = env.cfg
    name, url = resolve(cfg, target)
    p = await probe(env.http, url)
    if not p["ok"]:
        raise NodeError(
            f"{name or mask_url(url)} did not respond: {p['error']}. Still using "
            f"{cfg.node_name() or mask_url(cfg.solana.rpc_url)}."
        )
    if name is None:
        name = config_mod.name_from_url(url, set(cfg.solana.rpc_nodes))
    cfg.solana.rpc_nodes[name] = {"url": url, "cluster": p["cluster"]}
    old_cluster = cfg.solana.cluster
    cfg.solana.rpc_url = url
    cfg.solana.cluster = p["cluster"]
    _apply(env, persist)
    return {
        "name": name,
        "url": mask_url(url),
        "cluster_changed": old_cluster != p["cluster"],
        "previous_cluster": old_cluster,
        **p,
    }


def remove(env, name: str) -> None:
    nodes = env.cfg.solana.rpc_nodes
    if name not in nodes:
        raise NodeError(f"unknown node '{name}'")
    if nodes[name]["url"] == env.cfg.solana.rpc_url:
        raise NodeError("can't remove the active node; switch to another one first")
    del nodes[name]
    _apply(env)


def set_fallback(env, on: bool) -> None:
    env.cfg.solana.rpc_fallback = on
    _apply(env)
