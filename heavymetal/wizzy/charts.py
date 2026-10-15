"""QuickChart URLs for scroll charts (24h close line). Built locally: no network call to create a chart."""

from __future__ import annotations

import json
from urllib.parse import quote

QUICKCHART = "https://quickchart.io/chart"
OMEN_COLOR = {"cursed": "#ff4d6d", "hexed": "#c77dff", "murky": "#ffd166", "blessed": "#06d6a0", None: "#8ecae6"}


def price_chart_url(facts, omen: str | None = None, key: str = "") -> str | None:
    chart = (facts.extra or {}).get("chart") or {}
    closes = [c for c in chart.get("close") or [] if c is not None]
    if len(closes) < 2:
        return None
    sym = facts.token.symbol if facts.token and facts.token.symbol else "token"
    color = OMEN_COLOR.get(omen, OMEN_COLOR[None])
    cfg = {
        "type": "line",
        "data": {
            "labels": [f"-{len(closes) - 1 - i}h" for i in range(len(closes))],
            "datasets": [
                {
                    "label": f"${sym} 24h",
                    "data": closes,
                    "fill": False,
                    "borderColor": color,
                    "pointRadius": 0,
                    "borderWidth": 3,
                }
            ],
        },
        "options": {
            "legend": {"labels": {"fontColor": "#e9e4f0"}},
            "scales": {
                "xAxes": [{"ticks": {"fontColor": "#b8b0c8", "maxTicksLimit": 6}, "gridLines": {"display": False}}],
                "yAxes": [{"ticks": {"fontColor": "#b8b0c8"}, "gridLines": {"color": "rgba(255,255,255,0.08)"}}],
            },
        },
    }
    url = f"{QUICKCHART}?w=700&h=320&bkg=%231a1426&devicePixelRatio=2&c={quote(json.dumps(cfg, separators=(',', ':')))}"
    if key:
        url += f"&key={quote(key)}"
    return url
