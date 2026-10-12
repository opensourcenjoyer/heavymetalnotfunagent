"""Signals, Trenches, wiki and connector tools for the agent."""

from __future__ import annotations

from heavymetal.tools.registry import err, ok, tool


def _compact_pulse(p: dict) -> dict:
    t = p.get("today") or {}
    return {
        "fear_greed": {k: p["fear_greed"].get(k) for k in ("index", "band", "arms", "raw", "cohort", "notes")},
        "today": {
            k: t.get(k)
            for k in (
                "source",
                "smallcap_vol",
                "trench_vol",
                "total_vol",
                "top5_share",
                "top5",
                "pace",
                "pools",
                "kept",
                "drops",
                "coverage",
            )
        },
        "dune_day": {
            k: (p.get("dune") or {}).get(k) for k in ("day", "smallcap_vol", "trench_vol", "complete", "drops")
        }
        if p.get("dune")
        else None,
        "deltas_pct": p.get("deltas"),
        "regime_percentile": p.get("regime"),
        "ema7": p.get("ema7"),
        "ema14": p.get("ema14"),
        "last_14_days": [{k: r.get(k) for k in ("day", "smallcap", "source")} for r in (p.get("series") or [])[-14:]],
        "launches": p.get("launches"),
        "notes": p.get("notes"),
    }


@tool(
    "trenches_pulse",
    "Solana smallcap market pulse (Fair-style Trenches): smallcap volume (<= $200M FDV, majors/stables/equities/"
    "farms excluded, with what each gate dropped), top-5 tickers, pace, regime vs its own history, the launch "
    "hold/ceiling ladders and the Trench Fear & Greed index (0-100). Use for 'how is the market', sizing, timing.",
    {"refresh": {"type": "boolean", "default": False, "description": "force a fresh sweep (slow, ~1 min)"}},
    mainnet_only=True,
)
async def trenches_pulse(env, refresh: bool = False):
    from heavymetal.trenches.pulse import refresh as do_refresh

    try:
        p = await do_refresh(env, force=refresh)
    except Exception as e:  # noqa: BLE001
        return err(f"trenches unavailable: {e}")
    return ok(**_compact_pulse(p))


@tool(
    "signal_performance",
    "How the agent's signals actually performed, per entry verdict: hit rate to 2x (or `level`) within 24h/72h/7d "
    "(only matured signals count), median multiple since the call, died/rugged share, n per cohort (thin if n<5).",
    {
        "since_days": {"type": "number", "description": "only signals from the last N days"},
        "level": {"type": "integer", "default": 2, "description": "milestone multiple counted as a hit"},
    },
)
async def signal_performance(env, since_days: float | None = None, level: int = 2):
    from heavymetal.signals.performance import performance

    return ok(**performance(env.db, since_days, level))


@tool(
    "signal_runners",
    "Signals ranked by multiple since first call (current FDV / FDV at the call), with momentum state "
    "(running/cooling/falling), peak, top milestone and liquidity. Default liquidity floor $25K.",
    {
        "limit": {"type": "integer", "default": 15},
        "window_h": {"type": "number", "description": "only signals first called in the last N hours"},
        "rank": {"type": "string", "enum": ["multiple", "h24", "h1", "fdv", "liq"], "default": "multiple"},
        "min_liq": {"type": "number", "default": 25000},
        "tradeable_only": {"type": "boolean", "default": False, "description": "exclude HARD PASS verdicts"},
    },
)
async def signal_runners(
    env,
    limit: int = 15,
    window_h: float | None = None,
    rank: str = "multiple",
    min_liq: float = 25_000,
    tradeable_only: bool = False,
):
    from heavymetal.signals.performance import runners

    return ok(runners=runners(env.db, min(limit, 50), min_liq, window_h, rank, tradeable_only))


@tool(
    "signal_backtest",
    "Walk-forward backtest of the signal models (audit rules vs logistic model vs base rate) on matured signals, "
    "with lookahead-leak guards. backfill=true first fills outcomes from GeckoTerminal OHLCV (slow).",
    {
        "horizon_h": {"type": "number", "default": 72},
        "level": {"type": "integer", "default": 2},
        "backfill": {"type": "boolean", "default": False},
    },
)
async def signal_backtest(env, horizon_h: float = 72, level: int = 2, backfill: bool = False):
    from heavymetal.signals.backtest import backfill_outcomes, backtest

    bf = None
    if backfill and env.cluster == "mainnet" and getattr(env, "gecko", None):
        bf = await backfill_outcomes(env)
    return ok(backfill=bf, **backtest(env.db, horizon_h, level))


@tool(
    "farm_scan",
    "Run only the farm filter on a token (wash loops, zero-reserve pools, fee farming, round-tripping, thin crowds, "
    "flat loops). Returns is_farm, kind, reasons, warnings and the metrics used.",
    {"target": {"type": "string", "description": "mint, pair address or DexScreener/pump.fun link"}},
    ["target"],
    external=True,
)
async def farm_scan(env, target: str):
    from heavymetal.signals.farm import farm_check
    from heavymetal.solana.resolver import resolve_target

    try:
        r = await resolve_target(env, target)
    except Exception as e:  # noqa: BLE001
        return err(f"failed to resolve target: {e}")
    pair = None
    try:
        pairs = await env.dex.token_pairs(r.mint)
        pair = pairs[0] if pairs else None
    except Exception:  # noqa: BLE001
        pass
    res = await farm_check(env, r.mint, pair)
    return ok(mint=r.mint, **res.to_dict())


@tool(
    "scanner_status",
    "Background scanner status: running, feeds, pending launches, signals recorded today by verdict, recent alerts "
    "(new signals, milestones, dead/rugged) and the last error.",
)
async def scanner_status(env):
    sc = getattr(env, "scanner", None)
    if sc is None:
        return ok(running=False, note="scanner not started (REPL on mainnet starts it; /scanner on)")
    return ok(**sc.status())


@tool(
    "connector_status",
    "Which data connectors are configured (Dune, Birdeye, Helius are optional keys; GeckoTerminal, DefiLlama, "
    "DexScreener are keyless) and what each missing one would unlock. To add a key, ask the USER to run "
    "`/keys set <name>` themselves; never ask them to paste a key into the chat.",
)
async def connector_status(env):
    from heavymetal.data.connectors import missing, status

    return ok(
        connectors=status(env.cfg),
        missing=missing(env.cfg),
        how_to_add="Ask the user to type: /keys set <name>  (hidden input, saved to ~/.heavymetal/config.toml)",
    )


@tool(
    "wiki_search",
    "Search the agent wiki: launchpads (pump.fun, PumpSwap, bonk.fun, Meteora, Moonshot), farm patterns (wash loops, "
    "zero-reserve pools, fee farming, inorganic volume, volume bots), rug archetypes, past rug cases, methodology, "
    "and the user's notes / auto post-mortems.",
    {"query": {"type": "string"}, "limit": {"type": "integer", "default": 6}},
    ["query"],
    external=True,
)
async def wiki_search(env, query: str, limit: int = 6):
    from heavymetal.kb.wiki import get_wiki

    return ok(results=get_wiki().search(query, min(limit, 15)))


@tool(
    "wiki_read",
    "Read one wiki page by slug (e.g. farms/wash-loops, rugs/overview, launchpads/pump-fun). slug 'index' lists pages.",
    {"slug": {"type": "string"}},
    ["slug"],
    external=True,
)
async def wiki_read(env, slug: str):
    from heavymetal.kb.wiki import get_wiki

    w = get_wiki()
    if slug.strip() in ("", "list", "all"):
        return ok(pages=w.index())
    p = w.read(slug)
    if not p:
        return err(f"no page '{slug}'", suggestions=[r["slug"] for r in w.search(slug, 5)])
    return ok(**{k: p[k] for k in ("slug", "title", "tags", "summary", "verify", "origin", "body")})


@tool(
    "wiki_note",
    "Write a page to the user's wiki (~/.heavymetal/wiki, under notes/, cases/ or watch/): lessons from a trade, a "
    "rug post-mortem, a farm pattern you spotted. Only when the user asks or after a notable event.",
    {
        "slug": {"type": "string", "description": "e.g. cases/foo-rug or notes/entry-rules"},
        "title": {"type": "string"},
        "content": {"type": "string", "description": "markdown body"},
        "tags": {"type": "string"},
        "summary": {"type": "string"},
    },
    ["slug", "title", "content"],
)
async def wiki_note(env, slug: str, title: str, content: str, tags: str = "", summary: str = ""):
    from heavymetal.kb.wiki import get_wiki

    try:
        return ok(**get_wiki().note(slug, title, content, tags, summary))
    except ValueError as e:
        return err(str(e))
