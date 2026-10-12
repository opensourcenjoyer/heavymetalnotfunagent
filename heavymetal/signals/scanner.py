"""Always-on background scanner (mainnet, REPL). Finds launches, audits them in code (no LLM, no trades),
records signals, marks them until they age out, logs milestones, and refreshes Trenches.

Feeds:
  PumpPortal websocket   new pump.fun / bonk tokens and migrations -> pending, re-checked on a schedule
  GeckoTerminal          new_pools every scan_interval_s
Gates to become a signal: 24h volume >= signals.min_volume_h24 and liquidity >= signals.min_liquidity_usd.
Farms are recorded with verdict FARM (so the filter can be measured) but never alerted.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections import deque

RECHECK_S = (300, 900, 2700, 7200, 21600)  # pending launches: re-check at +5m, +15m, +45m, +2h, +6h
MIGRATION_RECHECK_S = (60, 300, 900, 3600)
MAX_PENDING = 3000


class Scanner:
    def __init__(self, env, on_alert=None):
        self.env = env
        self.on_alert = on_alert
        self.tasks: list[asyncio.Task] = []
        self.pending: dict[str, dict] = {}
        self.queued: set[str] = set()
        self.queue: asyncio.Queue = asyncio.Queue()
        self.alerts: deque = deque(maxlen=50)
        self.stats = {
            "ws_seen": 0,
            "gt_seen": 0,
            "audited": 0,
            "signals": 0,
            "farms": 0,
            "milestones": 0,
            "errors": 0,
            "marks": 0,
        }
        self.started_at: float | None = None
        self.ws_connected = False
        self.last_error: str | None = None
        self.last_scan: float | None = None
        self.last_mark: float | None = None
        self.pulse: dict | None = None
        self.last_pulse: float | None = None

    # ------------------------------------------------------------------ lifecycle
    @property
    def running(self) -> bool:
        return any(not t.done() for t in self.tasks)

    def start(self) -> bool:
        if self.running:
            return True
        if self.env.cluster != "mainnet":
            self.last_error = f"scanner needs mainnet (cluster: {self.env.cluster})"
            return False
        self.started_at = time.time()
        loops = (
            self._ws_loop,
            self._gt_loop,
            self._promote_loop,
            self._audit_worker,
            self._mark_loop,
            self._pulse_loop,
        )
        self.tasks = [asyncio.create_task(self._guard(fn), name=f"scanner:{fn.__name__}") for fn in loops]
        return True

    async def stop(self) -> None:
        for t in self.tasks:
            t.cancel()
        for t in self.tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        self.tasks = []
        self.ws_connected = False

    async def _guard(self, fn) -> None:
        """Keep a loop alive across errors; back off on repeated failures."""
        backoff = 5
        while True:
            try:
                await fn()
                return
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.stats["errors"] += 1
                self.last_error = f"{fn.__name__}: {type(e).__name__}: {e}"[:200]
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120)

    def _alert(self, kind: str, payload: dict) -> None:
        item = {"kind": kind, "ts": time.time(), **payload}
        self.alerts.append(item)
        cb = self.on_alert
        if callable(cb):
            with contextlib.suppress(Exception):
                cb(kind, item)

    def status(self) -> dict:
        from heavymetal.signals.ledger import counts_today

        return {
            "running": self.running,
            "since": self.started_at,
            "ws_connected": self.ws_connected,
            "pending": len(self.pending),
            "queued": self.queue.qsize(),
            "stats": dict(self.stats),
            "today": counts_today(self.env.db),
            "last_scan": self.last_scan,
            "last_mark": self.last_mark,
            "last_pulse": self.last_pulse,
            "last_error": self.last_error,
            "recent_alerts": list(self.alerts)[-10:],
        }

    # ------------------------------------------------------------------ feeds
    def _add_pending(self, mint: str, symbol: str | None, source: str, schedule=RECHECK_S) -> None:
        if not mint or mint in self.queued or self._known(mint):
            return
        if mint in self.pending:
            if source == "migration":  # a migration jumps the queue
                self.pending[mint].update(
                    source=source, schedule=list(MIGRATION_RECHECK_S), step=0, next=time.time() + MIGRATION_RECHECK_S[0]
                )
            return
        if len(self.pending) >= MAX_PENDING:
            oldest = min(self.pending, key=lambda k: self.pending[k]["first_seen"])
            self.pending.pop(oldest, None)
        now = time.time()
        self.pending[mint] = {
            "symbol": symbol,
            "source": source,
            "first_seen": now,
            "schedule": list(schedule),
            "step": 0,
            "next": now + schedule[0],
        }

    def _known(self, mint: str) -> bool:
        return self.env.db.conn.execute("SELECT 1 FROM signals WHERE mint=?", (mint,)).fetchone() is not None

    def _enqueue(self, mint: str, symbol: str | None, source: str) -> None:
        if mint in self.queued or self._known(mint):
            return
        self.pending.pop(mint, None)
        self.queued.add(mint)
        self.queue.put_nowait((mint, symbol, source))

    async def _ws_loop(self) -> None:
        import websockets

        from heavymetal.solana.pumpportal import DATA_WS

        backoff = 5
        while True:
            try:
                async with websockets.connect(DATA_WS, open_timeout=15, ping_interval=30) as ws:
                    await ws.send(json.dumps({"method": "subscribeNewToken"}))
                    await ws.send(json.dumps({"method": "subscribeMigration"}))
                    self.ws_connected, backoff = True, 5
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except (TypeError, ValueError):
                            continue
                        mint = msg.get("mint")
                        if not mint:
                            continue
                        self.stats["ws_seen"] += 1
                        if msg.get("txType") == "migrate" or "migrat" in str(msg.get("txType", "")).lower():
                            self._add_pending(mint, msg.get("symbol"), "migration", MIGRATION_RECHECK_S)
                        else:
                            self._add_pending(mint, msg.get("symbol"), "pump")
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.last_error = f"pumpportal ws: {e}"[:200]
            self.ws_connected = False
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)

    async def _gt_loop(self) -> None:
        from heavymetal.trenches.launches import upsert_launch

        s = self.env.cfg.signals
        while True:
            try:
                pools = await self.env.gecko.new_pools(pages=2)
                self.last_scan = time.time()
                for p in pools:
                    mint = p.get("mint")
                    if not mint:
                        continue
                    self.stats["gt_seen"] += 1
                    vol = (p.get("volume") or {}).get("h24") or 0
                    liq = p.get("liquidity_usd") or 0
                    if vol >= s.min_volume_h24:
                        upsert_launch(self.env.db, p, source="gt_new")
                    if vol >= s.min_volume_h24 and liq >= s.min_liquidity_usd:
                        self._enqueue(mint, p.get("symbol"), "gt_new")
                    else:
                        self._add_pending(mint, p.get("symbol"), "gt_new")
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.last_error = f"geckoterminal: {e}"[:200]
            await asyncio.sleep(max(20, s.scan_interval_s))

    async def _promote_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            try:
                await self.promote_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.last_error = f"dexscreener batch: {e}"[:200]

    async def promote_once(self) -> int:
        """Re-check due pending launches in one Dexscreener batch; queue the ones that passed the gates."""
        s = self.env.cfg.signals
        now = time.time()
        due = [m for m, p in self.pending.items() if p["next"] <= now][:90]
        if not due:
            return 0
        pairs = await self.env.dex.tokens_batch(due)
        promoted = 0
        for mint in due:
            p = self.pending.get(mint)
            if not p:
                continue
            pair = pairs.get(mint)
            vol = ((pair or {}).get("volume") or {}).get("h24") or 0
            liq = (pair or {}).get("liquidity_usd") or 0
            if pair and vol >= s.min_volume_h24 and liq >= s.min_liquidity_usd:
                self._enqueue(mint, (pair.get("base") or {}).get("symbol") or p["symbol"], p["source"])
                promoted += 1
                continue
            p["step"] += 1
            if p["step"] >= len(p["schedule"]):
                self.pending.pop(mint, None)
            else:
                p["next"] = p["first_seen"] + p["schedule"][p["step"]]
        return promoted

    async def _audit_worker(self) -> None:
        from heavymetal.signals.audit import audit_mint
        from heavymetal.signals.ledger import record_signal
        from heavymetal.trenches.launches import upsert_launch_from_pair

        alerts = set(self.env.cfg.signals.alerts)
        while True:
            mint, symbol, source = await self.queue.get()
            try:
                res = await audit_mint(self.env, mint, symbol, light=True)
                self.stats["audited"] += 1
                if not res["market"]:
                    continue
                sid, is_new = record_signal(self.env.db, res, source=source)
                if res["market"].get("pair"):
                    upsert_launch_from_pair(self.env.db, mint, res["market"], source=source)
                if not is_new:
                    continue
                self.stats["signals"] += 1
                if res["verdict_key"] == "FARM":
                    self.stats["farms"] += 1
                m = res["market"]
                payload = {
                    "id": sid,
                    "mint": mint,
                    "symbol": m.get("symbol") or symbol,
                    "verdict": res["verdict_key"],
                    "source": source,
                    "fdv": m.get("fdv") or m.get("market_cap"),
                    "liq": m.get("liquidity_usd"),
                    "vol_h24": m.get("volume_h24"),
                    "reason": (res["reasons"] or [""])[0],
                }
                if res["verdict_key"] in alerts:
                    self._alert("signal", payload)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.stats["errors"] += 1
                self.last_error = f"audit {mint[:8]}: {e}"[:200]
            finally:
                self.queued.discard(mint)
                await asyncio.sleep(2)  # spare RugCheck / RPC

    async def _mark_loop(self) -> None:
        await asyncio.sleep(20)
        while True:
            try:
                await self.mark_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.last_error = f"marks: {e}"[:200]
            await asyncio.sleep(max(60, self.env.cfg.signals.mark_interval_s))

    async def mark_once(self) -> dict:
        from heavymetal.signals.ledger import expire_old, mark, tracking

        s = self.env.cfg.signals
        db = self.env.db
        expire_old(db, s.track_days)
        sigs = tracking(db, s.track_days)
        if not sigs:
            return {"marked": 0}
        pairs = await self.env.dex.tokens_batch([x["mint"] for x in sigs])
        marked = 0
        for sig in sigs:
            p = pairs.get(sig["mint"])
            if not p:
                continue
            fdv = p.get("fdv") or p.get("market_cap")
            r = mark(
                db,
                sig,
                fdv,
                p.get("liquidity_usd"),
                p.get("price_usd"),
                (p.get("price_change") or {}).get("h1"),
                (p.get("price_change") or {}).get("h24"),
                (p.get("volume") or {}).get("h24"),
                min_liq=s.milestone_min_liq,
            )
            marked += 1
            for lv in r["milestones"]:
                self.stats["milestones"] += 1
                self._alert(
                    "milestone",
                    {
                        "id": sig["id"],
                        "mint": sig["mint"],
                        "symbol": sig["symbol"],
                        "level": lv,
                        "verdict": sig["verdict"],
                        "fdv": fdv,
                        "multiple": r["multiple"],
                    },
                )
            if r["status"]:
                self._alert(
                    "signal_end",
                    {"id": sig["id"], "symbol": sig["symbol"], "status": r["status"], "verdict": sig["verdict"]},
                )
                with contextlib.suppress(Exception):
                    from heavymetal.kb.wiki import write_postmortem

                    write_postmortem(db, sig["id"])
        self.stats["marks"] += marked
        self.last_mark = time.time()
        return {"marked": marked}

    async def _pulse_loop(self) -> None:
        from heavymetal.trenches.pulse import refresh

        await asyncio.sleep(45)
        while True:
            try:
                self.pulse = await refresh(self.env)
                self.last_pulse = time.time()
                fg = (self.pulse or {}).get("fear_greed") or {}
                self._alert(
                    "pulse",
                    {
                        "index": fg.get("index"),
                        "band": fg.get("band"),
                        "smallcap": (self.pulse.get("today") or {}).get("smallcap_vol"),
                    },
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.last_error = f"trenches: {e}"[:200]
            await asyncio.sleep(max(300, self.env.cfg.signals.pulse_interval_s))
