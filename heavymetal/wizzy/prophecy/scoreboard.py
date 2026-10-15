"""Weekly scoreboard: last week's prophecies graded, hit rate with n, thin samples flagged, wrong calls named."""

from __future__ import annotations

import datetime as dt
import json
import time

THIN = 5


def week_key(ts: float) -> str:
    y, w, _ = dt.datetime.fromtimestamp(ts, dt.UTC).isocalendar()
    return f"{y}-W{w:02d}"


def stats(wdb, since: float, until: float) -> dict:
    rows = wdb.all("SELECT * FROM prophecies WHERE resolved_ts>=? AND resolved_ts<? ORDER BY ts", (since, until))
    hits = [r for r in rows if r["outcome"] == "hit"]
    misses = [r for r in rows if r["outcome"] == "miss"]
    voids = [r for r in rows if r["outcome"] == "n/a"]
    graded = len(hits) + len(misses)
    by_kind: dict[str, dict] = {}
    for r in hits + misses:
        k = by_kind.setdefault(r["kind"], {"hit": 0, "miss": 0})
        k[r["outcome"]] += 1
    return {
        "n": graded,
        "hits": len(hits),
        "misses": len(misses),
        "voids": len(voids),
        "hit_rate": round(len(hits) / graded, 3) if graded else None,
        "thin": graded < THIN,
        "by_kind": by_kind,
        "wrong": [{"claim": r["claim"], "value": r["value_at_resolve"], "kind": r["kind"]} for r in misses],
        "right": [{"claim": r["claim"], "value": r["value_at_resolve"], "kind": r["kind"]} for r in hits],
    }


def _value(kind: str, v: float | None) -> str:
    if v is None:
        return "gone from the board"
    if kind == "narrative_share":
        return f"{round(v * 100, 2)}%"
    if kind == "top5_hold":
        return f"rank {int(v)}"
    return f"{v:,.0f}" if v >= 100 else f"{v:g}"


def text(s: dict, week: str) -> str:
    if s["n"] == 0:
        return f"📜 Prophecy scoreboard {week}: no prophecy matured this week ({s['voids']} voided)."
    rate = f"{round(s['hit_rate'] * 100)}%" if s["hit_rate"] is not None else "n/a"
    lines = [f"📜 Prophecy scoreboard {week}: {s['hits']}/{s['n']} came true ({rate})."]
    if s["thin"]:
        lines.append(f"A thin sample (fewer than {THIN}): read nothing into the rate yet.")
    for w in s["wrong"][:3]:
        lines.append(f"✗ Wrong: {w['claim']} It ended at {_value(w['kind'], w['value'])}.")
    for r in s["right"][:2]:
        lines.append(f"✓ {r['claim']}")
    if s["voids"]:
        lines.append(f"{s['voids']} voided for missing data.")
    lines.append("NFA · DYOR")
    return "\n".join(lines)


def build(wdb, now: float | None = None) -> tuple[str, dict, str]:
    now = now or time.time()
    s = stats(wdb, now - 7 * 86400, now)
    week = week_key(now)
    return week, s, text(s, week)


def save(wdb, week: str, s: dict, posted: str) -> bool:
    cur = wdb._x(
        "INSERT OR IGNORE INTO scoreboards(week, stats, posted_text, created_at) VALUES(?,?,?,?)",
        (week, json.dumps(s, default=str), posted, time.time()),
    )
    return bool(cur.rowcount)
