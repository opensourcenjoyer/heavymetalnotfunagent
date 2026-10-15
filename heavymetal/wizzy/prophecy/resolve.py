"""Grade matured prophecies with data stamped after the prophecy. Missing data voids; it never counts as a miss."""

from __future__ import annotations

import json
import time

from heavymetal.wizzy.prophecy import narratives


def due(wdb, now: float | None = None) -> list:
    now = now or time.time()
    return wdb.all("SELECT * FROM prophecies WHERE status='open' AND ts + horizon_h*3600 <= ? ORDER BY ts", (now,))


def _finish(wdb, pid: int, outcome: str, value: float | None, source: str) -> None:
    now = time.time()
    wdb._x(
        "UPDATE prophecies SET status=?, outcome=?, resolved_ts=?, value_at_resolve=? WHERE id=?",
        ("void" if outcome == "n/a" else "resolved", outcome, now, value, pid),
    )
    wdb._x("INSERT INTO prophecy_marks(prophecy_id, ts, value, source) VALUES(?,?,?,?)", (pid, now, value, source))


def compare(op: str, value: float, threshold: float) -> bool:
    return value >= threshold if op == ">=" else value > threshold if op == ">" else value < threshold


def _day_row(db, table: str, day: str):
    return db.conn.execute(f"SELECT * FROM {table} WHERE day=?", (day,)).fetchone()


async def resolve_one(ctx, row, sweep_cache: dict | None = None) -> str:
    """Grade one matured prophecy. Returns hit | miss | n/a."""
    subj = json.loads(row["subject"])
    db = ctx.env.db
    kind = row["kind"]
    if kind == "narrative_share":
        if sweep_cache is not None and "shares" in sweep_cache:
            shares = sweep_cache["shares"]
        else:
            from heavymetal.trenches.pulse import sweep

            try:
                _agg, pools = await sweep(ctx.env)
            except Exception:  # noqa: BLE001
                _finish(ctx.wdb, row["id"], "n/a", None, "sweep failed")
                return "n/a"
            shares = narratives.shares(ctx.wdb, narratives.kept(ctx.env, pools))
            if sweep_cache is not None:
                sweep_cache["shares"] = shares
        v = (shares.get(subj["narrative"]) or {}).get("share")
        value = v if v is not None else 0.0  # a narrative that vanished from the sweep has a 0% share
        outcome = "hit" if compare(row["op"], value, row["threshold"]) else "miss"
        _finish(ctx.wdb, row["id"], outcome, value, "gt sweep")
        return outcome
    if kind == "top5_hold":
        r = _day_row(db, "trench_days", subj["resolve_day"])
        if r is None or not r["top"] or (r["updated_at"] or 0) <= row["ts"]:
            _finish(ctx.wdb, row["id"], "n/a", None, "no trench_days row after the prophecy")
            return "n/a"
        syms = [t.get("symbol") for t in json.loads(r["top"])]
        outcome = "hit" if subj["symbol"] in syms else "miss"
        _finish(
            ctx.wdb,
            row["id"],
            outcome,
            float(syms.index(subj["symbol"]) + 1) if outcome == "hit" else None,
            "trench_days",
        )
        return outcome
    if kind in ("fg_direction", "volume_direction"):
        table, col = ("fg_days", "idx") if kind == "fg_direction" else ("trench_days", "smallcap_vol")
        r = _day_row(db, table, subj["resolve_day"])
        if r is None or r[col] is None or (r["updated_at"] or 0) <= row["ts"]:
            _finish(ctx.wdb, row["id"], "n/a", None, f"no {table} value after the prophecy")
            return "n/a"
        value = float(r[col])
        outcome = "hit" if compare(row["op"], value, row["threshold"]) else "miss"
        _finish(ctx.wdb, row["id"], outcome, value, table)
        return outcome
    _finish(ctx.wdb, row["id"], "n/a", None, "unknown kind")
    return "n/a"


async def resolve_due(ctx, now: float | None = None) -> dict:
    counts = {"hit": 0, "miss": 0, "n/a": 0}
    cache: dict = {}
    for row in due(ctx.wdb, now):
        counts[await resolve_one(ctx, row, cache)] += 1
    return counts
