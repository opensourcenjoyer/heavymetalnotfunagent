"""Interactive and command-line settings editor.
Configure Anthropic & OpenRouter keys, models, review modes, and trading parameters.
"""

from __future__ import annotations

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from rich.console import Console
from rich.table import Table

from heavymetal import config as config_mod
from heavymetal.decide import make_decider
from heavymetal.env import make_agent_llm

console = Console()

AVAILABLE_MODELS = [
    # Anthropic latest models
    "claude-sonnet-5-5",
    "claude-opus-5-5",
    "claude-fable-5-1",
    "claude-haiku-5-5",
    "claude-3-7-sonnet-latest",
    "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-latest",
    "claude-3-opus-latest",
    # OpenRouter models
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-chat",
    "deepseek/deepseek-r1",
    "anthropic/claude-3.5-sonnet",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "google/gemini-2.5-pro",
    "qwen/qwen-2.5-72b-instruct",
]

REVIEW_MODELS = [
    "typesafe/jev-1.13",
    "claude-haiku-5-5",
    "claude-3-5-haiku-latest",
    "deepseek/deepseek-v4-flash",
]


def _mask(k: str) -> str:
    if not k:
        return "[red]not set[/red]"
    if len(k) <= 8:
        return "set"
    return k[:6] + "…" + k[-4:]


def show_current_settings(cfg) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("key", style="dim")
    table.add_column("value", style="bold")

    table.add_row("agent model", cfg.llm.agent_model)
    table.add_row("provider", cfg.llm.provider)
    table.add_row("anthropic key", _mask(cfg.llm.anthropic_key))
    table.add_row("openrouter key", _mask(cfg.llm.api_key))
    table.add_row("review model", cfg.llm.review_model)
    table.add_row("review mode", cfg.review.mode)
    table.add_row("active rpc", cfg.node_name() or cfg.solana.rpc_url)
    table.add_row("slippage", f"{cfg.trade.slippage_pct}%")
    table.add_row("priority fee", f"{cfg.trade.priority_fee_sol} SOL")

    console.print()
    console.print("[bold]Current Settings[/bold]")
    console.print(table)
    console.print()


async def _ask(session: PromptSession, question: str, default: str = "", completer=None) -> str:
    display = f"{question} [{default}]: " if default else f"{question}: "
    try:
        val = await session.prompt_async(display, completer=completer)
        return val.strip() or default
    except (KeyboardInterrupt, EOFError):
        return default


async def run_settings(env) -> bool:
    cfg = env.cfg
    show_current_settings(cfg)
    console.print("[dim]Leave blank to keep current value. Ctrl+C to cancel.[/dim]\n")

    session = PromptSession()
    changed = False

    # 1. Model
    new_model = await _ask(
        session,
        "agent model",
        cfg.llm.agent_model,
        WordCompleter(AVAILABLE_MODELS, sentence=True),
    )
    if new_model != cfg.llm.agent_model:
        cfg.llm.agent_model = new_model
        if new_model.startswith("claude-") and cfg.llm.provider == "auto":
            cfg.llm.provider = "anthropic"
        changed = True

    # 2. Anthropic API Key
    console.print("[dim]  paste Anthropic key (sk-ant-...) or leave blank to keep[/dim]")
    ant_key = await _ask(
        session,
        "anthropic api key",
        "********" if cfg.llm.anthropic_key else "",
    )
    if ant_key and ant_key != "********":
        cfg.llm.anthropic_key = ant_key
        if cfg.llm.agent_model.startswith("claude-"):
            cfg.llm.provider = "anthropic"
        changed = True

    # 3. OpenRouter API Key
    console.print("[dim]  paste OpenRouter key (sk-or-...) or leave blank to keep[/dim]")
    or_key = await _ask(
        session,
        "openrouter api key",
        "********" if cfg.llm.api_key else "",
    )
    if or_key and or_key != "********":
        cfg.llm.api_key = or_key
        changed = True

    # 4. Review Model
    new_review_model = await _ask(
        session,
        "review model",
        cfg.llm.review_model,
        WordCompleter(REVIEW_MODELS, sentence=True),
    )
    if new_review_model != cfg.llm.review_model:
        cfg.llm.review_model = new_review_model
        changed = True

    # 5. Review Mode
    new_review_mode = await _ask(
        session,
        "review mode (gate|advise|off)",
        cfg.review.mode,
        WordCompleter(["gate", "advise", "off"]),
    )
    if new_review_mode in ("gate", "advise", "off") and new_review_mode != cfg.review.mode:
        cfg.review.mode = new_review_mode
        changed = True

    # 6. Slippage
    new_slippage = await _ask(
        session,
        "default slippage %",
        str(cfg.trade.slippage_pct),
    )
    try:
        s_val = float(new_slippage)
        if s_val != cfg.trade.slippage_pct:
            cfg.trade.slippage_pct = s_val
            changed = True
    except ValueError:
        pass

    # 7. Priority Fee
    new_fee = await _ask(
        session,
        "priority fee (SOL)",
        str(cfg.trade.priority_fee_sol),
    )
    try:
        f_val = float(new_fee)
        if f_val != cfg.trade.priority_fee_sol:
            cfg.trade.priority_fee_sol = f_val
            changed = True
    except ValueError:
        pass

    if changed:
        config_mod.save(cfg)
        env.agent_llm = make_agent_llm(cfg, cfg.llm.agent_model)
        env.decider = make_decider(cfg, env.http)
        console.print("\n[green]✓ Settings saved to ~/.heavymetal/config.toml[/green]\n")
    else:
        console.print("\n[dim]No changes.[/dim]\n")

    return changed


async def handle_settings_command(env, rest: list[str]) -> None:
    if not rest:
        await run_settings(env)
        return

    sub = rest[0].lower()
    cfg = env.cfg

    if sub in ("anthropic", "anthropic_key") and len(rest) == 2:
        cfg.llm.anthropic_key = rest[1]
        if cfg.llm.agent_model.startswith("claude-"):
            cfg.llm.provider = "anthropic"
        config_mod.save(cfg)
        env.agent_llm = make_agent_llm(cfg, cfg.llm.agent_model)
        console.print(f"[green]✓ Anthropic API key updated: {_mask(rest[1])}[/green]")

    elif sub in ("openrouter", "openrouter_key") and len(rest) == 2:
        cfg.llm.api_key = rest[1]
        config_mod.save(cfg)
        env.agent_llm = make_agent_llm(cfg, cfg.llm.agent_model)
        console.print(f"[green]✓ OpenRouter API key updated: {_mask(rest[1])}[/green]")

    elif sub == "model" and len(rest) == 2:
        cfg.llm.agent_model = rest[1]
        if rest[1].startswith("claude-") and cfg.llm.provider == "auto":
            cfg.llm.provider = "anthropic"
        config_mod.save(cfg)
        env.agent_llm = make_agent_llm(cfg, rest[1])
        console.print(f"[green]✓ Agent model set to: {rest[1]}[/green]")

    elif sub == "provider" and len(rest) == 2:
        if rest[1] in ("auto", "anthropic", "openrouter", "openai"):
            cfg.llm.provider = rest[1]
            config_mod.save(cfg)
            env.agent_llm = make_agent_llm(cfg, cfg.llm.agent_model)
            console.print(f"[green]✓ LLM Provider set to: {rest[1]}[/green]")
        else:
            console.print("[red]Unknown provider. Options: auto | anthropic | openrouter | openai[/red]")

    elif sub in ("show", "list"):
        show_current_settings(cfg)

    else:
        console.print(
            "[dim]usage: /settings | /settings model <name> | /settings anthropic <key> | /settings openrouter <key> | /settings show[/dim]"
        )
