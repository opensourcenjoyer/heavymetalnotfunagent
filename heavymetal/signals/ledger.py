"""Signal ledger: first call per token, periodic marks, milestones that are never deleted.

Rules (Fair-style):
- A token is a signal once. Its start (ts, FDV) never moves; a later audit updates `verdict_now` only.
  Performance is always scored on the entry `verdict`, so later information cannot leak into it.
- Multiple = current FDV / FDV when the signal was written. A valuation comparison, not a price return.
- Milestones 2x..100x need at least cfg.signals.milestone_min_liq of liquidity. Logged once per level;
  a pullback never deletes one. On the first observation only the highest level reached is logged,
  labelled first_observed.
"""

from __future__ import annotations

import json
import time

LEVELS = (2, 3, 5, 10, 20, 50, 100)
DEAD_LIQ = 1_000  # below this the pool is gone


def _row(r) -> dict | None:
    return dict(r) if r else None


def record_signal(
    db, audit: dict, source: str, model: str = "rules-v1", score: float | None = None
) -> tuple[int, bool]:
    """Insert the first call for a mint. Returns (signal_id, is_new). Later calls update verdict_now."""
    m = audit.get("market") or {}
    mint = audit["mint"]
    now = time.time()
    existing = db.conn.execute("SELECT id FROM signals WHERE mint=?", (mint,)).fetchone()
    if existing:
        db._x("UPDATE signals SET verdict_now=? WHERE id=?", (audit["verdict_key"], existing["id"]))
        return existing["id"], False
    cur = db._x(
        "INSERT INTO signals (ts, mint, symbol, name, pool, dex, source, verdict, reasons, fdv0, liq0, price0,"
        " features, model, score, verdict_now, status, last_ts, last_fdv, last_liq, last_price, chg_h1, chg_h24,"
        " peak_fdv, peak_ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            now,
            mint,
            m.get("symbol"),
            m.get("name"),
            m.get("pair"),
            m.get("dex"),
            source,
            audit["verdict_key"],
            json.dumps(audit.get("reasons") or []),
            m.get("fdv") or m.get("market_cap"),
            m.get("liquidity_usd"),
            m.get("price_usd"),
            json.dumps(audit.get("features") or {}, default=str),
            model,
            score,
            audit["verdict_key"],
            "tracking",
            now,
            m.get("fdv") or m.get("market_cap"),
            m.get("liquidity_usd"),
            m.get("price_usd"),
            m.get("price_change_h1"),
            m.get("price_change_h24"),
            m.get("fdv") or m.get("market_cap"),
            now,
        ),
    )
    return cur.lastrowid, True


def get_signal(db, key: str | int) -> dict | None:
    if isinstance(key, int) or str(key).isdigit():
        return _row(db.conn.execute("SELECT * FROM signals WHERE id=?", (int(key),)).fetchone())
    return _row(
        db.conn.execute("SELECT * FROM signals WHERE mint=? OR symbol=? ORDER BY ts DESC", (key, key)).fetchone()
    )


def recent_verdict(db, mint: str, within_s: float = 6 * 3600) -> str | None:
    r = db.conn.execute("SELECT verdict_now, last_ts, ts FROM signals WHERE mint=?", (mint,)).fetchone()
    if r and time.time() - max(r["ts"] or 0, r["last_ts"] or 0) <= within_s:
        return r["verdict_now"]
    return None


def tracking(db, max_age_days: float = 14) -> list[dict]:
    since = time.time() - max_age_days * 86400
    rows = db.conn.execute(
        "SELECT * FROM signals WHERE status='tracking' AND ts>=? ORDER BY ts DESC", (since,)
    ).fetchall()
    return [dict(r) for r in rows]


def expire_old(db, max_age_days: float = 14) -> int:
    cut = time.time() - max_age_days * 86400
    return db._x(
        "UPDATE signals SET status='expired', ended_at=? WHERE status='tracking' AND ts<?", (time.time(), cut)
    ).rowcount


def multiple(sig: dict, fdv: float | None = None) -> float | None:
    f0 = sig.get("fdv0")
    f = fdv if fdv is not None else sig.get("last_fdv")
    if not f0 or not f or f0 <= 0:
        return None
    return f / f0


def state(sig: dict) -> str:
    h1, h24 = sig.get("chg_h1"), sig.get("chg_h24")
    if sig.get("status") in ("dead", "rugged"):
        return sig["status"]
    if h1 is None or h24 is None:
        return "n/a"
    if h1 > 0 and h24 > 0:
        return "running"
    if h24 > 0:
        return "cooling"
    return "falling"


def mark(
    db,
    sig: dict,
    fdv: float | None,
    liq: float | None,
    price: float | None,
    chg_h1: float | None = None,
    chg_h24: float | None = None,
    vol_h24: float | None = None,
    ts: float | None = None,
    source: str = "live",
    min_liq: float = 25_000,
) -> dict:
    """Record a reading. Returns {'milestones': [levels newly hit], 'status': new status or None}."""
    ts = ts or time.time()
    sid = sig["id"]
    first = db.conn.execute("SELECT COUNT(*) n FROM milestones WHERE signal_id=?", (sid,)).fetchone()["n"] == 0 and (
        db.conn.execute("SELECT COUNT(*) n FROM signal_marks WHERE signal_id=?", (sid,)).fetchone()["n"] == 0
    )
    db._x(
        "INSERT INTO signal_marks (signal_id, ts, fdv, liq, price, vol_h24, source) VALUES (?,?,?,?,?,?,?)",
        (sid, ts, fdv, liq, price, vol_h24, source),
    )
    peak = sig.get("peak_fdv") or 0
    upd = {"last_ts": ts, "last_fdv": fdv, "last_liq": liq, "last_price": price, "chg_h1": chg_h1, "chg_h24": chg_h24}
    if source != "live":  # historical backfill: never overwrite the live "last" reading
        upd = {}
    if fdv and fdv > peak:
        upd.update(peak_fdv=fdv, peak_ts=ts)
    new_levels: list[int] = []
    mult = multiple(sig, fdv)
    if mult and liq is not None and liq >= min_liq:
        have = {r["level"] for r in db.conn.execute("SELECT level FROM milestones WHERE signal_id=?", (sid,))}
        reached = [lv for lv in LEVELS if mult >= lv and lv not in have]
        if reached:
            if first and source == "live" and sig.get("source") != "backfill":
                reached = [max(reached)]
            for lv in reached:
                db._x(
                    "INSERT OR IGNORE INTO milestones (signal_id, level, ts, fdv, first_observed) VALUES (?,?,?,?,?)",
                    (sid, lv, ts, fdv, 1 if first else 0),
                )
            new_levels = reached
    new_status = None
    if source == "live":
        liq0 = sig.get("liq0") or 0
        if liq is not None and liq < DEAD_LIQ:
            new_status = "rugged" if liq0 >= 5 * DEAD_LIQ else "dead"
        elif mult is not None and mult < 0.1:
            new_status = "dead"
        if new_status:
            upd.update(status=new_status, ended_at=ts)
    if upd:
        cols = ", ".join(f"{k}=?" for k in upd)
        db._x(f"UPDATE signals SET {cols} WHERE id=?", (*upd.values(), sid))
    return {"milestones": new_levels, "status": new_status, "multiple": mult}


def milestones(db, since: float | None = None, limit: int = 30) -> list[dict]:
    sql = (
        "SELECT m.*, s.symbol, s.mint, s.verdict, s.ts AS signal_ts, s.fdv0 FROM milestones m "
        "JOIN signals s ON s.id=m.signal_id WHERE 1=1"
    )
    args: list = []
    if since:
        sql += " AND m.ts>=?"
        args.append(since)
    sql += " ORDER BY m.ts DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in db.conn.execute(sql, args)]


def list_signals(db, limit: int = 50, verdict: str | None = None, since: float | None = None) -> list[dict]:
    sql, args = "SELECT * FROM signals WHERE 1=1", []
    if verdict:
        sql += " AND verdict=?"
        args.append(verdict)
    if since:
        sql += " AND ts>=?"
        args.append(since)
    sql += " ORDER BY ts DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in db.conn.execute(sql, args)]


def counts_today(db) -> dict:
    since = time.time() - 86400
    rows = db.conn.execute("SELECT verdict, COUNT(*) n FROM signals WHERE ts>=? GROUP BY verdict", (since,)).fetchall()
    return {r["verdict"]: r["n"] for r in rows}
