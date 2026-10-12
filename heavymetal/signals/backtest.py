"""Backtest the signal models on the ledger, with guards against lookahead leaks.

Leak guards (each violation drops the row and is counted in `guards`):
- features must be stamped at or before the signal (features.as_of <= signal ts + 5s)
- labels come only from milestones strictly after the signal and inside the horizon
- a signal enters only once its whole horizon has passed (no partially observed outcomes)
- one row per mint (the ledger keeps the first call only)
- walk-forward split by time, never random; feature scaling is fit on the train fold only
- OHLCV backfill uses candles that open after the signal, stamped at their close

Models: `rules` (the audit verdict), `logit` (plain-python logistic regression on the frozen
features), `base` (constant base rate).
"""

from __future__ import annotations

import json
import math
import time

from heavymetal.signals.ledger import mark

FEATURES = [
    ("liquidity_usd", "log"),
    ("fdv", "log"),
    ("age_hours", "log"),
    ("volume_h1", "log"),
    ("volume_h24", "log"),
    ("price_change_h1", "clip"),
    ("price_change_h24", "clip"),
    ("buy_ratio_h1", "raw"),
    ("buys_h1", "log"),
    ("top10_pct", "raw"),
    ("rug_score", "raw"),
    ("lp_locked_pct", "raw"),
    ("mint_auth_active", "bool"),
    ("is_token_2022", "bool"),
    ("turnover", "log"),
    ("swaps_per_wallet", "log"),
    ("wallets_h24", "log"),
    ("farm_warnings", "raw"),
    ("fake_warnings", "raw"),
    ("n_socials", "raw"),
]
RULE_SCORE = {"HIGH_CONVICTION": 1.0, "SPECULATIVE": 0.5}


def _tx(v, how: str) -> float | None:
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if how == "log":
        return math.log1p(max(v, 0))
    if how == "clip":
        return max(-100.0, min(v, 1000.0)) / 100
    if how == "bool":
        return 1.0 if v else 0.0
    return v


def dataset(db, horizon_h: float = 72, level: int = 2) -> tuple[list[dict], dict]:
    now = time.time()
    H = horizon_h * 3600
    guards = {"immature": 0, "features_after_signal": 0, "no_features": 0, "label_before_signal": 0}
    hits: dict[int, list[tuple[int, float]]] = {}
    for r in db.conn.execute("SELECT signal_id, level, ts FROM milestones"):
        hits.setdefault(r["signal_id"], []).append((r["level"], r["ts"]))
    rows = []
    for s in db.conn.execute("SELECT * FROM signals ORDER BY ts"):
        s = dict(s)
        if s["ts"] > now - H:
            guards["immature"] += 1
            continue
        try:
            f = json.loads(s["features"] or "{}")
        except json.JSONDecodeError:
            f = {}
        if not f:
            guards["no_features"] += 1
            continue
        if f.get("as_of") and f["as_of"] > s["ts"] + 5:
            guards["features_after_signal"] += 1
            continue
        hs = hits.get(s["id"], [])
        if any(t <= s["ts"] for _, t in hs):
            guards["label_before_signal"] += 1
            hs = [(lv, t) for lv, t in hs if t > s["ts"]]
        label = int(any(lv >= level and t - s["ts"] <= H for lv, t in hs))
        rows.append({"id": s["id"], "ts": s["ts"], "verdict": s["verdict"], "f": f, "y": label})
    return rows, guards


def _vec(f: dict) -> list[float | None]:
    return [_tx(f.get(k), how) for k, how in FEATURES]


class Logit:
    def __init__(self, l2: float = 0.01, lr: float = 0.3, epochs: int = 400):
        self.l2, self.lr, self.epochs = l2, lr, epochs

    def fit(self, X: list[list[float | None]], y: list[int]) -> Logit:
        k = len(FEATURES)
        cols = [[r[j] for r in X if r[j] is not None] for j in range(k)]
        self.mean = [sum(c) / len(c) if c else 0.0 for c in cols]
        self.sd = [
            (math.sqrt(sum((v - self.mean[j]) ** 2 for v in c) / len(c)) or 1.0) if c else 1.0
            for j, c in enumerate(cols)
        ]
        Z = [self._z(r) for r in X]
        self.w, self.b = [0.0] * k, 0.0
        n = len(Z)
        for _ in range(self.epochs):
            gw, gb = [0.0] * k, 0.0
            for z, t in zip(Z, y, strict=True):
                e = self._sig(sum(wi * zi for wi, zi in zip(self.w, z, strict=True)) + self.b) - t
                gb += e
                for j in range(k):
                    gw[j] += e * z[j]
            self.b -= self.lr * gb / n
            self.w = [w - self.lr * (g / n + self.l2 * w) for w, g in zip(self.w, gw, strict=True)]
        return self

    def _z(self, r):
        return [((v if v is not None else self.mean[j]) - self.mean[j]) / self.sd[j] for j, v in enumerate(r)]

    @staticmethod
    def _sig(x: float) -> float:
        return 1 / (1 + math.exp(-max(-30, min(30, x))))

    def predict(self, X) -> list[float]:
        return [self._sig(sum(w * z for w, z in zip(self.w, self._z(r), strict=True)) + self.b) for r in X]

    def weights(self) -> list[tuple[str, float]]:
        return sorted(((FEATURES[j][0], round(w, 3)) for j, w in enumerate(self.w)), key=lambda x: -abs(x[1]))


def auc(scores: list[float], y: list[int]) -> float | None:
    pos = [s for s, t in zip(scores, y, strict=True) if t]
    neg = [s for s, t in zip(scores, y, strict=True) if not t]
    if not pos or not neg:
        return None
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 3)


def _pr(pred: list[bool], y: list[int]) -> tuple[float | None, float | None]:
    tp = sum(1 for p, t in zip(pred, y, strict=True) if p and t)
    pp, ap = sum(pred), sum(y)
    return (round(tp / pp, 3) if pp else None), (round(tp / ap, 3) if ap else None)


def backtest(db, horizon_h: float = 72, level: int = 2, folds: int = 4, min_rows: int = 30) -> dict:
    rows, guards = dataset(db, horizon_h, level)
    out: dict = {"horizon_h": horizon_h, "level": level, "n": len(rows), "guards": guards, "folds": []}
    if len(rows) < min_rows or sum(r["y"] for r in rows) < 3:
        out["status"] = "insufficient"
        out["note"] = (
            f"need >= {min_rows} matured signals with >= 3 hits; have {len(rows)} "
            f"with {sum(r['y'] for r in rows)} hits. Keep the scanner running or /signals backfill."
        )
        return out
    rows.sort(key=lambda r: r["ts"])
    size = len(rows) // (folds + 1)
    agg: dict[str, dict[str, list]] = {m: {"scores": [], "y": [], "pred": []} for m in ("rules", "logit", "base")}
    model = None
    for i in range(1, folds + 1):
        train, test = rows[: i * size], rows[i * size : (i + 1) * size if i < folds else len(rows)]
        assert max(r["ts"] for r in train) <= min(r["ts"] for r in test), "walk-forward order violated"
        ytr, yte = [r["y"] for r in train], [r["y"] for r in test]
        base = sum(ytr) / len(ytr)
        model = Logit().fit([_vec(r["f"]) for r in train], ytr) if 0 < sum(ytr) < len(ytr) else None
        s_logit = model.predict([_vec(r["f"]) for r in test]) if model else [base] * len(test)
        cut = sorted(s_logit, reverse=True)[max(0, len(s_logit) // 5 - 1)] if s_logit else 1
        s_rules = [RULE_SCORE.get(r["verdict"], 0.0) for r in test]
        fold = {"train": len(train), "test": len(test), "base_rate": round(sum(yte) / len(yte), 3)}
        for name, sc, pred in (
            ("rules", s_rules, [s > 0 for s in s_rules]),
            ("logit", s_logit, [s >= cut for s in s_logit]),
            ("base", [base] * len(test), [False] * len(test)),
        ):
            p, rcl = _pr(pred, yte)
            fold[name] = {"auc": auc(sc, yte), "precision": p, "recall": rcl}
            agg[name]["scores"] += sc
            agg[name]["y"] += yte
            agg[name]["pred"] += pred
        out["folds"].append(fold)
    ally = agg["rules"]["y"]
    base_rate = sum(ally) / len(ally) if ally else None
    out["models"] = {}
    for name, a in agg.items():
        p, rcl = _pr(a["pred"], a["y"])
        out["models"][name] = {
            "auc": auc(a["scores"], a["y"]),
            "precision": p,
            "recall": rcl,
            "lift": round(p / base_rate, 2) if p and base_rate else None,
        }
    out["base_rate"] = round(base_rate, 3) if base_rate is not None else None
    out["weights"] = model.weights()[:8] if model else []
    out["status"] = "ok"
    return out


async def backfill_outcomes(env, limit: int = 25, min_liq: float | None = None) -> dict:
    """Fill marks for older signals from GeckoTerminal hourly OHLCV (wick-proof: hours with >= $500 traded)."""
    min_liq = min_liq if min_liq is not None else env.cfg.signals.milestone_min_liq
    db = env.db
    cut = time.time() - 3600
    sigs = [
        dict(r)
        for r in db.conn.execute(
            "SELECT * FROM signals WHERE ts<? AND pool IS NOT NULL AND price0>0 ORDER BY ts DESC LIMIT ?", (cut, limit)
        )
    ]
    done, marks, levels = 0, 0, 0
    for s in sigs:
        last = (
            db.conn.execute(
                "SELECT MAX(ts) t FROM signal_marks WHERE signal_id=? AND source='ohlcv'", (s["id"],)
            ).fetchone()["t"]
            or s["ts"]
        )
        hours = int((time.time() - last) / 3600) + 2
        if hours < 2:
            continue
        try:
            candles = await env.gecko.ohlcv(s["pool"], "hour", 1, min(hours, 1000))
        except Exception:  # noqa: BLE001
            continue
        done += 1
        gate_liq = max(s.get("liq0") or 0, s.get("last_liq") or 0)
        for c in candles:
            close_ts = c["ts"] + 3600
            if c["ts"] < s["ts"] or close_ts <= last or close_ts > time.time() or (c["volume"] or 0) < 500:
                continue
            fdv = s["fdv0"] * c["close"] / s["price0"] if s.get("fdv0") else None
            r = mark(db, s, fdv, gate_liq, c["close"], vol_h24=None, ts=close_ts, source="ohlcv", min_liq=min_liq)
            marks += 1
            levels += len(r["milestones"])
    return {"signals": done, "marks": marks, "milestones": levels}
