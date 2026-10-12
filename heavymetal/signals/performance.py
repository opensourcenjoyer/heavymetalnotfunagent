"""How the signals actually perform. Honesty rules: every rate prints its n; n < 5 is `thin`;
no data is None (n/a), never zero. A window only counts signals old enough to have lived through it."""

from __future__ import annotations

import statistics
import time

from heavymetal.signals.ledger import multiple, state

WINDOWS = {"24h": 86400, "72h": 3 * 86400, "7d": 7 * 86400}
THIN = 5
ORDER = ["HIGH_CONVICTION", "SPECULATIVE", "HIGH_RISK", "FARM", "HONEYPOT", "FAKE"]


def _hit_map(db) -> dict[int, list[tuple[int, float]]]:
    out: dict[int, list[tuple[int, float]]] = {}
    for r in db.conn.execute("SELECT signal_id, level, ts FROM milestones"):
        out.setdefault(r["signal_id"], []).append((r["level"], r["ts"]))
    return out


def _cohort_stats(sigs: list[dict], hits: dict, now: float, level: int = 2) -> dict:
    row: dict = {"n": len(sigs)}
    for name, w in WINDOWS.items():
        matured = [s for s in sigs if s["ts"] <= now - w]
        hit = [s for s in matured if any(lv >= level and t - s["ts"] <= w for lv, t in hits.get(s["id"], []))]
        row[f"hit_{name}"] = round(len(hit) / len(matured), 3) if matured else None
        row[f"n_{name}"] = len(matured)
        row[f"thin_{name}"] = 0 < len(matured) < THIN
    mults = [m for s in sigs if (m := multiple(s)) is not None]
    peaks = [s["peak_fdv"] / s["fdv0"] for s in sigs if s.get("peak_fdv") and s.get("fdv0")]
    row["median_multiple"] = round(statistics.median(mults), 3) if mults else None
    row["median_peak"] = round(statistics.median(peaks), 3) if peaks else None
    row["best_peak"] = round(max(peaks), 2) if peaks else None
    row["rugged"] = round(sum(s["status"] == "rugged" for s in sigs) / len(sigs), 3) if sigs else None
    row["dead"] = round(sum(s["status"] in ("dead", "rugged") for s in sigs) / len(sigs), 3) if sigs else None
    row["thin"] = 0 < len(sigs) < THIN
    return row


def performance(db, since_days: float | None = None, level: int = 2) -> dict:
    now = time.time()
    sql, args = "SELECT * FROM signals", []
    if since_days:
        sql += " WHERE ts>=?"
        args.append(now - since_days * 86400)
    sigs = [dict(r) for r in db.conn.execute(sql, args)]
    hits = _hit_map(db)
    by: dict[str, list[dict]] = {}
    for s in sigs:
        by.setdefault(s["verdict"], []).append(s)
    rows = [{"verdict": v, **_cohort_stats(by[v], hits, now, level)} for v in ORDER if v in by]
    rows += [{"verdict": v, **_cohort_stats(by[v], hits, now, level)} for v in by if v not in ORDER]
    tradeable = [s for s in sigs if s["verdict"] in ("HIGH_CONVICTION", "SPECULATIVE")]
    summary = {
        "all": _cohort_stats(sigs, hits, now, level),
        "tradeable": _cohort_stats(tradeable, hits, now, level),
        "filtered_out": _cohort_stats([s for s in sigs if s not in tradeable], hits, now, level),
    }
    return {"level": level, "rows": rows, "summary": summary, "n": len(sigs)}


def runners(
    db,
    limit: int = 20,
    min_liq: float = 25_000,
    window_h: float | None = None,
    rank: str = "multiple",
    tradeable_only: bool = False,
) -> list[dict]:
    now = time.time()
    sql, args = "SELECT * FROM signals WHERE 1=1", []
    if window_h:
        sql += " AND ts>=?"
        args.append(now - window_h * 3600)
    if tradeable_only:
        sql += " AND verdict IN ('HIGH_CONVICTION','SPECULATIVE')"
    sigs = [dict(r) for r in db.conn.execute(sql, args)]
    hits = _hit_map(db)
    out = []
    for s in sigs:
        if min_liq and (s.get("last_liq") or 0) < min_liq:
            continue
        m = multiple(s)
        out.append(
            {
                "id": s["id"],
                "symbol": s["symbol"],
                "mint": s["mint"],
                "verdict": s["verdict"],
                "verdict_now": s["verdict_now"],
                "source": s["source"],
                "age_h": round((now - s["ts"]) / 3600, 1),
                "multiple": round(m, 2) if m is not None else None,
                "peak": round(s["peak_fdv"] / s["fdv0"], 2) if s.get("peak_fdv") and s.get("fdv0") else None,
                "top_level": max((lv for lv, _ in hits.get(s["id"], [])), default=None),
                "state": state(s),
                "chg_h1": s.get("chg_h1"),
                "chg_h24": s.get("chg_h24"),
                "fdv": s.get("last_fdv"),
                "fdv0": s.get("fdv0"),
                "liq": s.get("last_liq"),
                "status": s["status"],
            }
        )
    key = {
        "multiple": lambda r: r["multiple"] or 0,
        "h24": lambda r: r["chg_h24"] or -1e9,
        "h1": lambda r: r["chg_h1"] or -1e9,
        "fdv": lambda r: r["fdv"] or 0,
        "liq": lambda r: r["liq"] or 0,
    }.get(rank, lambda r: r["multiple"] or 0)
    return sorted(out, key=key, reverse=True)[:limit]
