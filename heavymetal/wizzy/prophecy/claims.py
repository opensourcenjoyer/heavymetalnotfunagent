"""Claim generation: every prophecy is a measurable statement with a frozen baseline (no LLM involved).

Kinds:
  narrative_share  a narrative's share of gated smallcap volume is >= / < its baseline share after 72h
  top5_hold        a ticker in today's top 5 is still in the top 5 three days later (trench_days.top)
  fg_direction     the Trench Fear & Greed index is higher / lower in 7 days (fg_days)
  volume_direction gated smallcap volume is higher / lower in 7 days than today's banked value (trench_days)
No buy/sell language, no price targets.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field

from heavymetal.wizzy.prophecy.narratives import OTHER

KINDS = ("narrative_share", "top5_hold", "fg_direction", "volume_direction")


@dataclass
class Claim:
    kind: str
    subject: dict
    claim: str
    metric: str
    op: str  # ">=", "<", "in_top5"
    threshold: float | None
    horizon_h: float
    baseline: dict
    features: dict = field(default_factory=dict)


def day_str(ts: float, plus_days: int = 0) -> str:
    return (dt.datetime.fromtimestamp(ts, dt.UTC) + dt.timedelta(days=plus_days)).strftime("%Y-%m-%d")


def narrative_claim(shares: dict, overall_pace: float | None, now: float) -> Claim | None:
    cands = [(n, v) for n, v in shares.items() if n != OTHER and v["share"] and v["share"] >= 0.05 and v["pools"] >= 3]
    if not cands:
        return None
    n, v = max(cands, key=lambda kv: kv[1]["share"])
    rising = (v["pace"] or 0) > (overall_pace or 0)
    op = ">=" if rising else "<"
    word = "holds or grows" if rising else "shrinks"
    pct = round(v["share"] * 100, 2)
    return Claim(
        kind="narrative_share",
        subject={"narrative": n},
        claim=f"The {n} narrative's share of smallcap volume ({pct}% now) {word} over the next 72 hours.",
        metric="narrative_share",
        op=op,
        threshold=v["share"],
        horizon_h=72,
        baseline={"share": v["share"], "pace": v["pace"], "overall_pace": overall_pace, "pools": v["pools"]},
        features={"as_of": now},
    )


def top5_claim(top5: list[dict], now: float) -> Claim | None:
    if not top5:
        return None
    t = top5[0]
    pct = round((t.get("share") or 0) * 100, 2)
    return Claim(
        kind="top5_hold",
        subject={"symbol": t["symbol"], "resolve_day": day_str(now, 3)},
        claim=f"${t['symbol']} ({pct}% of smallcap volume today) is still in the top 5 by volume in 3 days.",
        metric="in_top5",
        op="in_top5",
        threshold=None,
        horizon_h=72,
        baseline={"symbol": t["symbol"], "share": t.get("share"), "rank": 1},
        features={"as_of": now},
    )


def fg_claim(fg: dict, now: float) -> Claim | None:
    idx = fg.get("index")
    mom = (fg.get("arms") or {}).get("momentum")
    if idx is None or mom is None:
        return None
    up = mom >= 50
    return Claim(
        kind="fg_direction",
        subject={"resolve_day": day_str(now, 7)},
        claim=f"The Trench Fear & Greed index ({idx} now) is {'higher' if up else 'lower'} in 7 days.",
        metric="fg_index",
        op=">" if up else "<",
        threshold=float(idx),
        horizon_h=168,
        baseline={"index": idx, "momentum": mom, "band": fg.get("band")},
        features={"as_of": now},
    )


def volume_claim(today_smallcap: float | None, ema7: float | None, ema14: float | None, now: float) -> Claim | None:
    if not today_smallcap or ema7 is None or ema14 is None:
        return None
    up = ema7 >= ema14
    return Claim(
        kind="volume_direction",
        subject={"resolve_day": day_str(now, 7)},
        claim=f"Smallcap trench volume is {'higher' if up else 'lower'} in 7 days than today's banked level.",
        metric="smallcap_vol",
        op=">" if up else "<",
        threshold=float(today_smallcap),
        horizon_h=168,
        baseline={"smallcap": today_smallcap, "ema7": ema7, "ema14": ema14, "day": day_str(now)},
        features={"as_of": now},
    )


def candidates(pulse: dict, shares: dict, now: float | None = None) -> list[Claim]:
    now = now or time.time()
    today = pulse.get("today") or {}
    out = [
        narrative_claim(shares, today.get("pace"), now),
        top5_claim(today.get("top5") or [], now),
        fg_claim(pulse.get("fear_greed") or {}, now),
        volume_claim(today.get("smallcap_vol"), pulse.get("ema7"), pulse.get("ema14"), now),
    ]
    return [c for c in out if c is not None]


def store(wdb, c: Claim, posted_text: str | None = None, public_at: float | None = None) -> int:
    import json

    now = c.features.get("as_of") or time.time()
    return wdb._x(
        "INSERT INTO prophecies(ts, kind, subject, claim, metric, op, threshold, horizon_h, baseline, features, "
        "posted_text, public_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            now,
            c.kind,
            json.dumps(c.subject),
            c.claim,
            c.metric,
            c.op,
            c.threshold,
            c.horizon_h,
            json.dumps(c.baseline, default=str),
            json.dumps(c.features, default=str),
            posted_text,
            public_at,
        ),
    ).lastrowid


def next_kind(wdb) -> list[str]:
    """Rotate kinds so the scoreboard covers all of them: least-used kinds first."""
    counts = {r["kind"]: r["n"] for r in wdb.all("SELECT kind, COUNT(*) AS n FROM prophecies GROUP BY kind")}
    return sorted(KINDS, key=lambda k: (counts.get(k, 0), KINDS.index(k)))
