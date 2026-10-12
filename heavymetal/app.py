"""REPL: prompt_toolkit input, slash commands, Ctrl+C interrupts the agent without quitting."""

from __future__ import annotations

import asyncio
import signal

import httpx
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.markup import escape
from rich.text import Text

from heavymetal import config as config_mod
from heavymetal import paths
from heavymetal.agent import run_turn
from heavymetal.commands_signals import (
    SIGNALS_HELP,
    TRENCHES_HELP,
    AlertSink,
    fg_cmd,
    keys_cmd,
    scanner_cmd,
    signals_cmd,
    start_scanner,
    trenches_cmd,
    wiki_cmd,
)
from heavymetal.env import AgentEnv, build_env
from heavymetal.memory import DB
from heavymetal.solana import nodes, wallet
from heavymetal.tools.wallet import holdings
from heavymetal.ui import (
    BANNER,
    GOODBYE,
    Panel,
    StreamRenderer,
    console,
    make_event_handler,
    render_markdown,
    review_detail,
    table,
    ts,
)

COMMANDS = [
    "/help",
    "/wallet",
    "/history",
    "/positions",
    "/reviews",
    "/cost",
    "/settings",
    "/model",
    "/new",
    "/sessions",
    "/resume",
    "/review",
    "/zdr",
    "/rpc",
    "/rpc use",
    "/rpc add",
    "/rpc rm",
    "/rpc fallback",
    "/trenches",
    "/trenches refresh",
    "/trenches sql",
    "/trenches calibrate",
    "/fg",
    "/signals",
    "/signals runners",
    "/signals perf",
    "/signals backtest",
    "/signals backfill",
    "/signals farms",
    "/signals recent",
    "/scanner",
    "/scanner on",
    "/scanner off",
    "/scanner mark",
    "/wiki",
    "/keys",
    "/keys set",
    "/keys rm",
    "/exit",
]
HELP = f"""[bold]Chat[/bold]: just type what you want, e.g.
  check https://dexscreener.com/solana/4k3Dyj... and buy 0.05 SOL with 2x TP and 30% SL
  check the trending coins and rug-check the top 3
  scan wallet <address>     ·     send 0.1 SOL to <address>     ·     launch a token called ...
[bold]Commands[/bold]
  /wallet            balances           /history     trade ledger      /positions     open TP/SL positions
  /settings          configure keys & models (Anthropic, OpenRouter, RPC, slippage)
  /reviews \\[id]      swap reviews       /cost        tokens & $ this session          /new  /sessions
  /model \\[agent|review] <model-id>      /review gate|advise|off        /zdr           check ZDR endpoints
  /rpc               list + test RPC nodes      /rpc use <name|url>   switch node
  /rpc add <name> <url>    /rpc rm <name>       /rpc fallback on|off  auto-failover on same cluster
[bold]Signals & market[/bold]
  {escape(TRENCHES_HELP)}     Solana smallcap pulse + Fear & Greed
  {escape(SIGNALS_HELP)}
  /scanner \\[on|off|mark]   background launch scanner     /wiki \\[query|slug]   launchpads, farms, rugs
  /keys \\[set|rm <name>]    data connectors (dune, dune_query_id, birdeye, helius)
  Ctrl+C  interrupt the agent        /exit  quit"""


async def zdr_models(http: httpx.AsyncClient) -> set[str]:
    r = await http.get("https://openrouter.ai/api/v1/endpoints/zdr", timeout=20)
    r.raise_for_status()
    return {e.get("model_id") for e in r.json().get("data", [])}


async def zdr_check(env: AgentEnv, verbose: bool = False) -> None:
    if not (env.cfg.llm.zdr and getattr(env.agent_llm, "is_openrouter", False)):
        if verbose:
            console.print("[yellow]ZDR enforcement is off (llm.zdr=false or non-OpenRouter endpoint)[/yellow]")
        return
    try:
        ok_models = await zdr_models(env.http)
    except Exception as e:  # noqa: BLE001
        console.print(f"[dim]ZDR check skipped: {e}[/dim]")
        return
    for role, model in (("agent", env.cfg.llm.agent_model), ("review", env.cfg.llm.review_model)):
        if model in ok_models:
            if verbose:
                console.print(f"[green]✓ {role}: {model} has ZDR endpoints[/green]")
        else:
            console.print(f"[red]✗ {role}: {model} has no ZDR endpoint; requests will fail while llm.zdr=true[/red]")


async def run_with_interrupt(coro):
    loop = asyncio.get_running_loop()
    task = asyncio.ensure_future(coro)
    try:
        loop.add_signal_handler(signal.SIGINT, task.cancel)
    except NotImplementedError:
        pass
    try:
        return await task, False
    except asyncio.CancelledError:
        return None, True
    finally:
        try:
            loop.remove_signal_handler(signal.SIGINT)
        except NotImplementedError:
            pass


async def show_wallet(env: AgentEnv) -> None:
    h = await holdings(env, env.address)
    console.print(f"[bold]{h['address']}[/bold]  ({env.cluster})")
    console.print(
        f"SOL {h['sol']:.6f}"
        + (f"  (${h['sol'] * h['sol_usd_price']:.2f})" if h["sol_usd_price"] else "")
        + (f"   total ${h['total_usd']}" if h["total_usd"] is not None else "")
    )
    if h["tokens"]:
        table("tokens", ["mint", "amount", "usd"], [[t["mint"], t["amount"], t["usd"]] for t in h["tokens"]])


async def show_positions(env: AgentEnv) -> None:
    from heavymetal.solana.positions import evaluate_open_positions

    with console.status("checking open positions & live prices…"):
        pos_list = await evaluate_open_positions(env)
    if not pos_list:
        console.print("[dim]no active open positions (use buy_with_tpsl to open one)[/dim]")
        return
    rows = []
    for p in pos_list:
        entry = f"${p['entry_price_usd']:.6f}" if p.get("entry_price_usd") else "?"
        curr = f"${p['current_price_usd']:.6f}" if p.get("current_price_usd") else "?"
        pnl = f"{p['pnl_pct']:+.1f}%" if p.get("pnl_pct") is not None else "?"
        color = "green" if (p.get("pnl_pct") or 0) >= 0 else "red"
        tp = f"{p.get('tp_multiple')}x (${p.get('tp_price_usd', 0):.6f})" if p.get("tp_price_usd") else "none"
        sl = f"-{p.get('sl_pct')}% (${p.get('sl_price_usd', 0):.6f})" if p.get("sl_price_usd") else "none"
        trig = p.get("action_trigger", "HOLD")
        rows.append(
            [str(p["id"]), p["symbol"], p["mint"][:8] + "…", entry, curr, f"[{color}]{pnl}[/{color}]", tp, sl, trig]
        )
    table(
        "active positions",
        ["id", "symbol", "mint", "entry", "current", "pnl", "tp target", "sl target", "signal"],
        rows,
    )


def show_cost(env: AgentEnv) -> None:
    rows = env.db.usage(env.session_id)
    table(
        "usage this session",
        ["role", "model", "calls", "in", "out", "$"],
        [[r["role"], r["model"], r["calls"], r["tin"], r["tout"], f"{r['cost'] or 0:.5f}"] for r in rows],
    )


async def handle_command(env: AgentEnv, line: str, sink: AlertSink | None = None) -> bool:
    """Returns False to exit."""
    cmd, *rest = line.split()
    if cmd in ("/exit", "/quit"):
        return False
    if cmd == "/help":
        console.print(HELP)
    elif cmd == "/wallet":
        await show_wallet(env)
    elif cmd == "/history":
        rows = env.db.trades(25)
        table(
            "trade ledger",
            ["time", "tool", "action", "amount", "unit", "mint/to", "status", "signature"],
            [
                [
                    ts(r["ts"]),
                    r["tool"],
                    r["action"],
                    r["amount"],
                    r["unit"],
                    r["counterparty"] or r["mint"],
                    r["status"],
                    (r["signature"] or "")[:20],
                ]
                for r in rows
            ],
        )
    elif cmd == "/positions":
        await show_positions(env)
    elif cmd == "/reviews":
        rows = env.db.reviews(50 if rest else 15)
        if rest:
            match = [r for r in rows if str(r["id"]) == rest[0]]
            review_detail(match[0]) if match else console.print("no such review")
        else:
            table(
                "swap reviews",
                ["id", "time", "tool", "verdict", "model", "s", "$"],
                [
                    [
                        r["id"],
                        ts(r["ts"]),
                        r["tool"],
                        r["verdict"],
                        r["model"],
                        r["latency_s"],
                        f"{r['cost_usd'] or 0:.5f}",
                    ]
                    for r in rows
                ],
            )
    elif cmd == "/cost":
        show_cost(env)
    elif cmd == "/settings":
        from heavymetal.settings import handle_settings_command

        await handle_settings_command(env, rest)
    elif cmd == "/new":
        env.session_id = env.db.new_session()
        env.messages.clear()
        env.research.clear()
        console.print(f"[dim]new session {env.session_id}[/dim]")
    elif cmd == "/sessions":
        table(
            "sessions",
            ["id", "started", "messages"],
            [[s["id"], ts(s["created_at"]), s["n"]] for s in env.db.list_sessions()],
        )
    elif cmd == "/resume" and rest:
        env.session_id = rest[0]
        env.messages[:] = env.db.messages(rest[0])
        console.print(f"[dim]resumed {rest[0]} ({len(env.messages)} messages)[/dim]")
    elif cmd == "/model":
        if len(rest) == 2 and rest[0] in ("agent", "review"):
            setattr(env.cfg.llm, f"{rest[0]}_model", rest[1])
            if rest[0] == "agent":
                from heavymetal.env import make_agent_llm

                env.agent_llm = make_agent_llm(env.cfg, rest[1])
            else:
                from heavymetal.decide import make_decider

                env.decider = make_decider(env.cfg, env.http)
            config_mod.save(env.cfg)
            console.print(f"[green]{rest[0]} model → {rest[1]}[/green]")
            await zdr_check(env)
        else:
            console.print(
                f"agent: {env.cfg.llm.agent_model}\nreview: {env.cfg.llm.review_model}\n"
                "usage: /model agent|review <model-id> (e.g. claude-sonnet-5-5 or deepseek/deepseek-v4-flash)"
            )
    elif cmd == "/review":
        if rest and rest[0] in ("gate", "advise", "off"):
            env.cfg.review.mode = rest[0]
            config_mod.save(env.cfg)
        console.print(f"review mode: {env.cfg.review.mode}  actions: {env.cfg.review.actions}")
    elif cmd == "/zdr":
        await zdr_check(env, verbose=True)
    elif cmd == "/rpc":
        await rpc_command(env, rest)
    elif cmd == "/trenches":
        await trenches_cmd(env, rest)
    elif cmd == "/fg":
        await fg_cmd(env)
    elif cmd == "/signals":
        await signals_cmd(env, rest)
    elif cmd == "/scanner":
        await scanner_cmd(env, rest, sink)
    elif cmd == "/wiki":
        wiki_cmd(env, rest)
    elif cmd == "/keys":
        await keys_cmd(env, rest)
    else:
        console.print("unknown command, /help")
    return True


async def show_rpc(env: AgentEnv) -> None:
    with console.status("probing RPC nodes…"):
        rows = await nodes.status(env)
    table(
        f"RPC nodes (failover {'on' if env.cfg.solana.rpc_fallback else 'off'})",
        ["", "name", "cluster", "latency", "slot", "url"],
        [
            [
                "●" if r["active"] else ("↳" if r["fallback"] else ""),
                r["name"],
                r["cluster"],
                f"{r['latency_ms']} ms" if r["ok"] else "[red]down[/red]",
                r.get("slot") or r.get("error", "")[:40],
                r["url"],
            ]
            for r in rows
        ],
    )
    if env.rpc.url != env.cfg.solana.rpc_url:
        console.print(f"[yellow]currently serving from {env.cfg.node_name(env.rpc.url)} after a failover[/yellow]")
    console.print("[dim]● active  ↳ failover · /rpc use <name|url> · /rpc add <name> <url> · /rpc rm <name>[/dim]")


async def rpc_command(env: AgentEnv, rest: list[str]) -> None:
    sub = rest[0] if rest else ""
    try:
        if sub in ("", "list", "test", "status"):
            await show_rpc(env)
        elif sub == "use" and len(rest) == 2:
            with console.status("checking node…"):
                r = await nodes.use(env, rest[1])
            console.print(
                f"[green]RPC → {r['name']}[/green] {r['url']} ({r['cluster']}, {r['latency_ms']} ms, "
                f"slot {r['slot']}) · {len(env.rpc.urls) - 1} failover node(s)"
            )
            if r["cluster_changed"]:
                console.print(
                    f"[bold yellow]cluster changed {r['previous_cluster']} → {r['cluster']}: balances, "
                    f"trading and tools now run on {r['cluster']}[/bold yellow]"
                )
        elif sub == "add" and len(rest) == 3:
            with console.status("checking node…"):
                r = await nodes.add(env, rest[1], rest[2])
            console.print(
                f"[green]saved {r['name']}[/green] {r['url']} ({r['cluster']}, {r['latency_ms']} ms)"
                f" · switch with /rpc use {r['name']}"
            )
        elif sub in ("rm", "remove") and len(rest) == 2:
            nodes.remove(env, rest[1])
            console.print(f"removed {rest[1]}")
        elif sub == "fallback" and len(rest) == 2 and rest[1] in ("on", "off"):
            nodes.set_fallback(env, rest[1] == "on")
            console.print(
                f"failover {rest[1]} · serving list: "
                f"{', '.join(env.cfg.node_name(u) or 'custom' for u in env.rpc.urls)}"
            )
        else:
            console.print(
                "usage: /rpc | /rpc use <name|url> | /rpc add <name> <url> | /rpc rm <name> | /rpc fallback on|off"
            )
    except nodes.NodeError as e:
        console.print(f"[red]{e}[/red]")


async def bootstrap(cluster: str | None, rpc: str | None, resume: bool) -> AgentEnv:
    import sys

    cfg = config_mod.load()
    if not (cfg.llm.api_key or cfg.llm.anthropic_key) and sys.stdin.isatty():
        cfg = config_mod.wizard(cfg)
    kp, created = wallet.load_or_create()
    db = DB()
    sid = (db.latest_session() if resume else None) or db.new_session()
    env = build_env(cfg, kp, db, sid)
    if resume:
        env.messages[:] = db.messages(sid)
    target = rpc or (
        next((n for n, v in cfg.solana.rpc_nodes.items() if v["cluster"] == cluster), None) if cluster else None
    )
    if cluster and not target:
        raise SystemExit(f"no saved {cluster} node; add one with /rpc add")
    if target:  # this run only; /rpc use makes it permanent
        try:
            await nodes.use(env, target, persist=False)
        except nodes.NodeError as e:
            raise SystemExit(f"--rpc: {e}") from None
    if created:
        console.print(
            f"[bold green]Created the agent wallet:[/bold green] {env.address}\n"
            f"[dim]key file: {paths.wallet_path()} (chmod 600). Back it up; whoever has it controls "
            f"the funds.[/dim]"
        )
    return env


async def main(
    cluster: str | None = None, rpc: str | None = None, resume: bool = False, prompt: str | None = None
) -> None:
    env = await bootstrap(cluster, rpc, resume)
    renderer = StreamRenderer(console)
    try:
        if prompt:  # one-shot mode
            tool_log: list[str] = []
            env.on_event = make_event_handler(renderer, tool_log)
            text = await run_turn(env, prompt, renderer.on_delta)
            renderer.stop()
            if not renderer.streamed_anything and text:
                render_markdown(text)
            return

        console.print(BANNER)
        console.print(
            f"[dim]agent {env.cfg.llm.agent_model} · review {env.cfg.llm.review_model} "
            f"({env.cfg.review.mode}) · ZDR {'on' if env.cfg.llm.zdr else 'off'} · {env.cluster} via "
            f"{env.cfg.node_name() or 'custom'} (+{len(env.rpc.urls) - 1} failover) · "
            f"session {env.session_id}[/dim]"
        )
        try:
            await show_wallet(env)
        except Exception as e:  # noqa: BLE001
            console.print(f"[yellow]wallet: {env.address} (balance unavailable: {e})[/yellow]")
        await zdr_check(env)
        sink = AlertSink()
        if env.cfg.signals.scanner and env.cluster == "mainnet":
            console.print(f"[dim]{start_scanner(env, sink)} · /scanner off to stop[/dim]")
        console.print(
            "[dim]cmds: /wallet /positions /history /trenches /signals /scanner /wiki /keys /rpc /cost /model /exit[/dim]"
        )
        console.print("[dim]tip:  Ctrl+C during agent = interrupt | paste DexScreener link to audit[/dim]\n")

        from heavymetal.ui_signals import toolbar

        session = PromptSession(
            history=FileHistory(str(paths.history_path())),
            completer=WordCompleter(COMMANDS, sentence=True),
            bottom_toolbar=lambda: toolbar(env),
            refresh_interval=5,
        )
        while True:
            sink.busy = False
            sink.flush()
            try:
                with patch_stdout(raw=True):  # scanner alerts print above the prompt while you type
                    line = (await session.prompt_async(">> ")).strip()
            except (EOFError, KeyboardInterrupt):
                console.print(GOODBYE)
                break
            sink.busy = True
            if not line:
                continue
            if line.startswith("/"):
                try:
                    if not await handle_command(env, line, sink):
                        console.print(GOODBYE)
                        break
                except Exception as e:  # noqa: BLE001
                    console.print(f"[red]{e}[/red]")
                continue

            renderer.reset()
            tool_log: list[str] = []
            env.on_event = make_event_handler(renderer, tool_log)

            try:
                text, interrupted = await run_with_interrupt(run_turn(env, line, renderer.on_delta))
            except Exception as e:  # noqa: BLE001
                renderer.stop()
                console.print(f"[red]error: {e}[/red]")
                continue
            finally:
                renderer.stop()

            if interrupted:
                console.print("[yellow]Interrupted.[/yellow]\n")
                continue

            print()
            # Compact trace replay of what tools did during the run
            for log_line in tool_log:
                console.print(f"[dim]{log_line}[/dim]")
            if tool_log:
                print()

            # Reasoning block
            if renderer.reasoning_text.strip():
                reasoning = renderer.reasoning_text.strip()
                if len(reasoning) > 4000:
                    reasoning = "…" + reasoning[-4000:]
                console.print(
                    Panel(
                        Text(reasoning, style="dim italic"),
                        title="[dim]🧠 reasoning[/dim]",
                        border_style="dim",
                        padding=(0, 1),
                    )
                )
                print()

            # If content was already streamed, don't re-render it
            if not renderer.streamed_anything and text:
                render_markdown(text)
            print()
    finally:
        if env.scanner is not None:
            await env.scanner.stop()
        await env.http.aclose()
        console.print("[dim]bye[/dim]")
