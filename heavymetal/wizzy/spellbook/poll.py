"""Spellbook poller: due watches -> fresh snapshot -> diff -> deduped events -> owl messages (via the job queue)."""

from __future__ import annotations

import asyncio
import json
import time

from heavymetal.solana.txsummary import summarize_tx
from heavymetal.wizzy import jobs
from heavymetal.wizzy.spellbook import watches as W
from heavymetal.worker import BackgroundWorker

CADENCE_S = {"free": 900, "inner": 180}


def due(ctx, now: float | None = None) -> list:
    now = now or time.time()
    out = []
    for w in ctx.wdb.all("SELECT * FROM watches WHERE active=1 AND kind != 'unlock'"):
        cadence = CADENCE_S["inner" if ctx.wdb.tier(w["user_id"]) == "inner" else "free"]
        if w["last_check"] is None or now - w["last_check"] >= cadence:
            out.append(w)
    return out


def _state(ctx, wid: int) -> dict:
    r = ctx.wdb.one("SELECT state FROM watch_snapshots WHERE watch_id=?", (wid,))
    return json.loads(r["state"]) if r else {}


def _save_state(ctx, wid: int, state: dict) -> None:
    ctx.wdb._x(
        "INSERT INTO watch_snapshots(watch_id, ts, state) VALUES(?,?,?) "
        "ON CONFLICT(watch_id) DO UPDATE SET ts=excluded.ts, state=excluded.state",
        (wid, time.time(), json.dumps(state, default=str)),
    )


async def check(ctx, w, liq_batch: dict | None = None) -> list[dict]:
    env = ctx.env
    params = json.loads(w["params"])
    old = _state(ctx, w["id"])
    kind = w["kind"]
    if kind == "holders_moved":
        rows, info = await asyncio.gather(env.rpc.largest_holders(w["target"]), env.rpc.mint_info(w["target"]))
        new = W.holders_state(rows, info["supply"])
        events = W.holders_diff(old, new, params) if old else []
        _save_state(ctx, w["id"], new)
        return events
    if kind == "liquidity_drop":
        pair = (liq_batch or {}).get(w["target"])
        if pair is None:
            batch = await env.dex.tokens_batch([w["target"]])
            pair = batch.get(w["target"])
        events, state = W.liquidity_diff(old, (pair or {}).get("liquidity_usd"), params)
        _save_state(ctx, w["id"], state)
        return events
    if kind == "authority_change":
        info = await env.rpc.mint_info(w["target"])
        new = {"mint_authority": info.get("mint_authority"), "freeze_authority": info.get("freeze_authority")}
        events = W.authority_diff(old, new)
        _save_state(ctx, w["id"], new)
        return events
    if kind == "wallet_moves":
        sigs = await env.rpc.signatures(w["target"], 20)
        last = old.get("last_sig")
        if last is None:  # first look: remember where we are, alert only on what comes after
            _save_state(ctx, w["id"], {"last_sig": sigs[0]["signature"] if sigs else None})
            return []
        fresh = []
        for s in sigs:
            if s["signature"] == last:
                break
            fresh.append(s)
        txs = []
        for s in fresh[:10]:
            tx = await env.rpc.transaction(s["signature"])
            if tx:
                txs.append(summarize_tx(tx, w["target"]))
        if sigs:
            _save_state(ctx, w["id"], {"last_sig": sigs[0]["signature"]})
        return W.wallet_events(txs, params)
    return []


def label_for(ctx, w) -> str:
    row = ctx.wdb.one("SELECT symbol FROM subjects WHERE key=?", (w["target"],))
    return f"${row['symbol']}" if row and row["symbol"] else f"{w['target'][:4]}…{w['target'][-4:]}"


def deliver(ctx, w, events: list[dict]) -> int:
    """Store events (deduped) and queue owls, honouring the watch's cooldown. Returns owls queued."""
    now = time.time()
    sent = 0
    for ev in events:
        cur = ctx.wdb._x(
            "INSERT OR IGNORE INTO watch_events(watch_id, event_key, ts, payload) VALUES(?,?,?,?)",
            (w["id"], ev["key"], now, json.dumps(ev, default=str)),
        )
        if not cur.rowcount:
            continue
        fresh = ctx.wdb.one("SELECT last_fired FROM watches WHERE id=?", (w["id"],))
        if fresh["last_fired"] and now - fresh["last_fired"] < w["cooldown_s"]:
            continue
        jobs.enqueue(
            ctx.wdb,
            "tg_dm",
            {"chat_id": w["chat_id"], "text": W.owl_text(w, ev, label_for(ctx, w))},
            dedupe_key=f"owl:{w['id']}:{ev['key']}",
        )
        ctx.wdb._x("UPDATE watches SET last_fired=? WHERE id=?", (now, w["id"]))
        ctx.wdb._x("UPDATE watch_events SET delivered=1 WHERE watch_id=? AND event_key=?", (w["id"], ev["key"]))
        sent += 1
    return sent


async def poll_once(ctx, now: float | None = None) -> int:
    ws = due(ctx, now)
    if not ws:
        return 0
    liq_mints = [w["target"] for w in ws if w["kind"] == "liquidity_drop"]
    batch = {}
    if liq_mints:
        try:
            batch = await ctx.env.dex.tokens_batch(sorted(set(liq_mints)))
        except Exception:  # noqa: BLE001
            batch = {}
    sem = asyncio.Semaphore(4)
    owls = 0

    async def one(w):
        nonlocal owls
        async with sem:
            try:
                events = await check(ctx, w, batch)
            except Exception:  # noqa: BLE001 - one bad target never stops the others
                events = []
            ctx.wdb._x("UPDATE watches SET last_check=? WHERE id=?", (time.time(), w["id"]))
            owls += deliver(ctx, w, events)

    await asyncio.gather(*(one(w) for w in ws))
    return owls


class SpellbookWorker(BackgroundWorker):
    name = "wizzy-spellbook"

    def __init__(self, ctx, svc=None):
        super().__init__(ctx.env)
        self.ctx = ctx

    def loops(self):
        return (self._loop,)

    async def _loop(self) -> None:
        while True:
            await poll_once(self.ctx)
            await asyncio.sleep(60)
