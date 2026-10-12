"""Trench Fear & Greed: the weighted average of four 0-100 readings.

  smallcap volume   1/3  how much money moves through smallcaps, against a FIXED normal
  volume momentum   1/3  last 7 days vs the 7 before (the one arm read against the tape's own past)
  hold ladder       1/6  how much of what launched still holds 2/3/5/7/10x its day-1 close (3-day avg), fixed normal
  ceiling ladder    1/6  how big launch tops get, fixed normal

Fixed normals mean the same market reads the same number, and a market that stays dead keeps reading
fear; with two thirds of the weight on fixed arms, momentum can turn the needle but cannot lift a dead
market to neutral. Momentum sits out for 10 days after a change in how volume is counted that moved the
total by more than a tenth. The single number is withheld when fewer than 8 launches can be scored.

The default normals are an initial calibration (2026-10, GeckoTerminal top-200 sweep of Solana);
re-measure them on your own ledger with `/trenches calibrate` and set them in [signals].
"""

from __future__ import annotations

import math

WEIGHTS = {"volume": 1 / 3, "momentum": 1 / 3, "hold": 1 / 6, "ceiling": 1 / 6}
# volume: ~ the 2025-10..2026-10 median of Solana smallcap volume (DefiLlama x the measured smallcap share);
# hold / ceiling: first guesses until the launch registry has a month of history. Re-measure: /trenches calibrate
DEFAULT_NORMALS = {"volume": 700_000_000.0, "hold": 0.06, "ceiling": 0.22}
# greed side wider than the fear side, wider still on the ceiling: (fear scale, greed scale) in log units
SCALES = {
    "volume": (math.log(2.0), math.log(3.0)),
    "momentum": (math.log(1.5), math.log(1.6)),
    "hold": (math.log(2.0), math.log(3.0)),
    "ceiling": (math.log(2.0), math.log(4.0)),
}
BANDS = [
    (25, "EXTREME FEAR", "red3"),
    (45, "FEAR", "dark_orange"),
    (55, "NEUTRAL", "grey62"),
    (75, "GREED", "green3"),
    (100, "EXTREME GREED", "cyan3"),
]
MIN_TAPES = 8
SIT_OUT_DAYS = 10
EPS = 0.005


def band(v: float | None) -> tuple[str, str]:
    if v is None:
        return "N/A", "grey50"
    for hi, word, color in BANDS:
        if v <= hi:
            return word, color
    return BANDS[-1][1], BANDS[-1][2]


def score(x: float | None, normal: float, arm: str) -> float | None:
    if x is None or normal is None or normal <= 0:
        return None
    z = math.log((x + EPS * normal) / (normal + EPS * normal))
    down, up = SCALES[arm]
    return round(50 + 50 * math.tanh(z / (up if z > 0 else down)), 1)


def normals(cfg) -> dict:
    s = cfg.signals
    return {
        "volume": s.fg_volume_normal or DEFAULT_NORMALS["volume"],
        "hold": s.fg_hold_normal or DEFAULT_NORMALS["hold"],
        "ceiling": s.fg_ceiling_normal or DEFAULT_NORMALS["ceiling"],
    }


def momentum_ratio(series: list[dict]) -> tuple[float | None, str | None]:
    """series: [{'day','smallcap','version'}] oldest first, one row per day. Returns (ratio, why-not)."""
    vals = [r for r in series if r.get("smallcap")]
    if len(vals) < 14:
        return None, f"needs 14 days of history, has {len(vals)}"
    # most recent definition change: the first row of the current version run
    cur = vals[-1].get("version")
    i = len(vals) - 1
    while i > 0 and vals[i - 1].get("version") == cur:
        i -= 1
    if i > 0 and len(vals) - i <= SIT_OUT_DAYS:
        prev = [r["smallcap"] for r in vals[max(0, i - 7) : i]]
        new = [r["smallcap"] for r in vals[i : i + 7]]
        if prev and new and abs(sum(new) / len(new) / (sum(prev) / len(prev)) - 1) > 0.10:
            return None, "sitting out: the volume definition changed in the last 10 days"
    a = sum(r["smallcap"] for r in vals[-7:]) / 7
    b = sum(r["smallcap"] for r in vals[-14:-7]) / 7
    return (a / b if b > 0 else None), None


def compute(cfg, series: list[dict], ladder: dict, hold_hist: list[float] | None = None) -> dict:
    """series: daily smallcap volume rows oldest first. ladder: trenches.launches.ladders().
    hold_hist: recent daily hold depths (oldest first) for the 3-day average."""
    N = normals(cfg)
    latest = next((r for r in reversed(series) if r.get("smallcap")), None)
    vol_x = latest["smallcap"] if latest else None
    mom_x, mom_note = momentum_ratio(series)
    hd = [h for h in (hold_hist or []) if h is not None][-2:] + (
        [ladder["hold_depth"]] if ladder.get("hold_depth") is not None else []
    )
    hold_x = sum(hd) / len(hd) if hd else None
    arms = {
        "volume": score(vol_x, N["volume"], "volume"),
        "momentum": score(mom_x, 1.0, "momentum") if mom_x is not None else None,
        "hold": score(hold_x, N["hold"], "hold"),
        "ceiling": score(ladder.get("ceiling_depth"), N["ceiling"], "ceiling"),
    }
    raw = {"volume": vol_x, "momentum": mom_x, "hold": hold_x, "ceiling": ladder.get("ceiling_depth")}
    present = {k: v for k, v in arms.items() if v is not None}
    cohort = ladder.get("cohort") or 0
    idx = None
    if present and cohort >= MIN_TAPES:
        wsum = sum(WEIGHTS[k] for k in present)
        idx = round(sum(WEIGHTS[k] * v for k, v in present.items()) / wsum)
    word, color = band(idx)
    notes = []
    if mom_note:
        notes.append(f"momentum: {mom_note}")
    if cohort < MIN_TAPES:
        notes.append(f"index withheld: {cohort} scored launches, needs {MIN_TAPES} (the arms still read)")
    if not cfg.signals.fg_volume_normal:
        notes.append("normals are the built-in initial calibration; /trenches calibrate re-measures them")
    return {
        "index": idx,
        "band": word,
        "color": color,
        "arms": arms,
        "raw": raw,
        "weights": WEIGHTS,
        "normals": N,
        "cohort": cohort,
        "min_tapes": MIN_TAPES,
        "notes": notes,
    }


def calibrate(series: list[dict], hold_hist: list[float], ceil_hist: list[float]) -> dict:
    """Suggest normals = the median of what the ledger has measured (needs >= 30 days to mean much)."""

    def med(xs):
        xs = sorted(x for x in xs if x)
        return xs[len(xs) // 2] if xs else None

    return {
        "fg_volume_normal": med([r.get("smallcap") for r in series]),
        "fg_hold_normal": med(hold_hist),
        "fg_ceiling_normal": med(ceil_hist),
        "days": len(series),
        "hold_days": len([h for h in hold_hist if h]),
    }
