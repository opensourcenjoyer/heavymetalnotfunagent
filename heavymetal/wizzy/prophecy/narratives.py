"""Narrative tagging for sweep pools (keyword taxonomy, cached) and volume share per narrative."""

from __future__ import annotations

import re
import time

TAXONOMY: dict[str, list[str]] = {
    "AI agents": ["ai", "agent", "agents", "gpt", "llm", "agi", "neural", "sentient", "bot", "robot", "virtual"],
    "dogs": ["dog", "doge", "inu", "shib", "wif", "pup", "puppy", "corgi", "bonk", "shiba", "woof"],
    "cats": ["cat", "cats", "kitty", "kitten", "meow", "popcat", "mew", "nyan", "michi"],
    "frogs": ["pepe", "frog", "toad", "ribbit", "kek"],
    "political": ["trump", "maga", "biden", "kamala", "president", "melania", "vote", "usa", "america"],
    "celebrity": ["elon", "musk", "kanye", "drake", "taylor", "celeb", "diddy"],
    "gaming": ["game", "gaming", "play", "pixel", "quest", "arcade"],
    "anime": ["anime", "waifu", "chan", "kun", "senpai"],
    "DeFi": ["swap", "yield", "stake", "staked", "dao", "lend", "finance", "fi"],
    "RWA": ["gold", "rwa", "estate", "bond", "treasury", "silver"],
}
OTHER = "other"


def words(*texts: str | None) -> set[str]:
    out: set[str] = set()
    for t in texts:
        if t:
            out |= set(re.findall(r"[a-z0-9]+", t.lower()))
            out |= {w for w in re.findall(r"[a-z]{3,}", t.lower())}
    return out


def tag(symbol: str | None, name: str | None) -> str:
    ws = words(symbol, name)
    joined = f"{(symbol or '').lower()} {(name or '').lower()}"
    for narrative, keys in TAXONOMY.items():
        for k in keys:
            if k in ws or (len(k) >= 4 and k in joined):
                return narrative
    return OTHER


def tag_cached(wdb, mint: str, symbol: str | None, name: str | None) -> str:
    row = wdb.one("SELECT narrative FROM narrative_tags WHERE mint=?", (mint,))
    if row:
        return row["narrative"]
    n = tag(symbol, name)
    wdb._x(
        "INSERT OR REPLACE INTO narrative_tags(mint, narrative, method, tagged_at) VALUES(?,?, 'keyword', ?)",
        (mint, n, time.time()),
    )
    return n


def shares(wdb, kept_pools: list[dict]) -> dict[str, dict]:
    """{narrative: {vol24, vol6, pools, share, pace}} over gated sweep pools (excluding 'other')."""
    tot = sum((p.get("volume") or {}).get("h24") or 0 for p in kept_pools)
    out: dict[str, dict] = {}
    for p in kept_pools:
        n = tag_cached(wdb, p.get("mint") or p.get("pool") or "?", p.get("symbol"), p.get("name"))
        v = out.setdefault(n, {"vol24": 0.0, "vol6": 0.0, "pools": 0})
        v["vol24"] += (p.get("volume") or {}).get("h24") or 0
        v["vol6"] += (p.get("volume") or {}).get("h6") or 0
        v["pools"] += 1
    for v in out.values():
        v["share"] = round(v["vol24"] / tot, 4) if tot else None
        v["pace"] = round(v["vol6"] * 4 / v["vol24"], 3) if v["vol24"] else None
        v["vol24"] = round(v["vol24"], 2)
        v["vol6"] = round(v["vol6"], 2)
    return out


def kept(env, pools: list[dict]) -> list[dict]:
    from heavymetal.trenches.gates import gate_pool

    return [p for p in pools if not gate_pool(p, env.cfg)[0]]
