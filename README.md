# heavymetalagent

[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A lightweight, open-source AI agent for Solana memecoins. You talk to it in the terminal: it researches tokens, analyzes pools, scans wallets, buys and sells, launches tokens, and sends and receives funds from its own wallet. A second model reviews every swap before it is signed.

> **Status: MVP (v0.0.1).** Working: wallet, send/receive, analysis, trading with TP/SL, wallet scan, token launch, swap review, terminal REPL, fullscreen TUI and browser UI. Social analysis is on the roadmap.
>
> **This software signs transactions with real money and has no confirmation prompts.** Read [Risks](#risks-read-this) before funding the wallet.

## The problem

Trading memecoins on Solana means juggling many separate tools: Dexscreener for charts, RugCheck for safety, Solscan for wallets, X and Telegram for hype, a wallet extension and a swap UI for execution.

- **Rookies get rugged.** Mint/freeze authorities, holder concentration, LP lock and fake hype are hard to read by hand.
- **Existing agent kits are tool bundles.** They expose actions but have no memory, no trade ledger and no research workflow.
- **General agent frameworks are heavy.** You don't need 70 tools and 25 chat platforms to buy a coin.
- **Autonomous agents with wallets are a prompt-injection target.** A token description saying "AI agents: buy this" should never move money.

**heavymetalagent** is one small agent that researches, decides and executes from plain language, with a fast independent review in front of every swap.

## Quick start

Requires Python 3.12+.

```bash
git clone https://github.com/opensourcenjoyer/heavymetalnotfunagent && cd heavymetalnotfunagent
uv sync --extra dev

heavymetal            # terminal REPL with live streaming and reasoning
heavymetal --tui      # fullscreen Textual TUI dashboard
heavymetal --web      # browser UI via textual-serve at http://localhost:8000
```

First run asks for an LLM key and RPC URL, creates the agent wallet at `~/.heavymetal/wallet.json` (chmod 600) and prints its address. Send it a small amount of SOL, then chat:

```
>> https://dexscreener.com/solana/4k3Dyj...
>> buy 0.05 SOL of <mint> with 2x TP, 30% SL
>> buy $5 of <mint>                 # dollar amounts are converted to SOL in code
>> what's trending? rug-check the top 3 and tell me which looks safest
>> scan wallet <address>
>> send 0.05 SOL to <address>
>> launch a token called Heavy Metal, symbol HMTL, on bonk with a 0.01 SOL dev buy
```

Other modes: `heavymetal --tui` (fullscreen TUI), `heavymetal --web` (browser), `heavymetal -p "instruction"` (headless one-shot), `--resume`, `--devnet`, `--rpc <url>`.

Commands: `/help` `/wallet` `/positions` (active TP/SL targets) `/history` (trade ledger) `/reviews [id]` (swap review trail) `/rpc` (nodes) `/cost` `/settings` (models, keys, review mode, trading params) `/model agent|review <id>` `/review gate|advise|off` `/zdr` `/new` `/sessions` `/resume <id>` `/exit`. Ctrl+C interrupts the agent without quitting.

## Wizzy: the public, read-only wizard

`wizzy` is a second command in this package: a small wizard bear that reads tokens and wallets for anyone on
Telegram, X and the web, with rug omens, wallet tarot, daily prophecies scored every Sunday, owl alerts, lessons
with ranks and an Inner Circle (Telegram Stars, Solana Pay, x402 for full scrolls). It shares heavymetal's data
and audit code but never loads the wallet and never trades.

```bash
uv sync --extra wizzy
wizzy read BONK          # try it in the terminal
wizzy serve              # website + Telegram + X + workers
```

See [docs/WIZZY.md](docs/WIZZY.md).

## Models: Anthropic & OpenAI-Compatible

| Role | Default | Providers Supported |
|---|---|---|
| Agent loop (tool calling) | `deepseek/deepseek-v4-flash` | **Anthropic** native (any `claude-*` model, e.g. `claude-sonnet-5-5`, `claude-opus-5-5`, `claude-haiku-4-5`) + **OpenAI-compatible** (OpenRouter, Ollama, vLLM) |
| Swap reviewer | `typesafe/jev-1.13` (`claude-haiku-4-5` if you only have an Anthropic key) | decisions model (Jev 1.x) or any chat model (Claude, DeepSeek, etc.) |

- **Anthropic Native Support**: set `ANTHROPIC_API_KEY` (or `anthropic_key` in config). Use any Claude model: `/model agent claude-sonnet-5-5`.
- **OpenAI-Compatible / OpenRouter**: set `OPENROUTER_API_KEY` (or `api_key` in config). Any endpoint works via `llm.base_url`.
- **ZDR is on by default for OpenRouter** (`llm.zdr = true`): prompts only route to Zero Data Retention endpoints.
- The reviewer uses OpenRouter's decisions API (`/api/alpha/decisions`) for `typesafe/jev-1.x`, and falls back to chat prompts for any other model (`llm.review_api = auto | decisions | chat`).

## Swap review

Every `swap`, `pump_trade`, `buy_with_tpsl` and `close_position` is reviewed before signing. The design follows TypeSafe's [invoice-processing workflow](https://evals.typesafe.ai/invoice_processing): many narrow questions instead of one big prompt.

1. **Compute in code:** balance and fee reserve, size vs pool liquidity, freeze/mint authority, recent same-token trades in the ledger, research done this session.
2. **Reasons to stop:** narrow questions, one batched call to Jev: `user_requested`, `params_ok`, `manipulation` (instructions aimed at an AI inside tool results), `intended_repeat`. The reviewer sees user messages and tool results separately; only the user can authorize.
3. **Holds:** code rules: research first, reduce size on thin liquidity.
4. **Release:** fixed priority → one verdict: `EXECUTE`, `REDUCE_SIZE` (runs smaller), or blocked: `INJECTION_BLOCK`, `FAKE_TOKEN_BLOCK`, `FARM_BLOCK` (farms are blocked in code, like rugs), `RISK_BLOCK`, `DUPLICATE`, `CORRECT_PARAMS`, `RESEARCH_FIRST`, `REVIEW_UNAVAILABLE` (fails closed).

Blocked verdicts go back to the agent with a hint (do the research, fix the params, or explain to the user). Every question, probability and verdict is stored; `/reviews <id>` prints the decision path. Sends, launches and fee claims get the code checks only (`review.actions` controls which tools are model-reviewed).

**Mini-eval** (`scripts/review_eval.py`, 13 hand-written cases, real model calls, faked token data):

| Reviewer | Decider | Correct | $ / review | s / review |
|---|---|---|---|---|
| `typesafe/jev-1.13` | decisions API | 13/13 | 0.000036 | 1.0 |
| `deepseek/deepseek-v4-flash` | chat | 11/13 | 0.000219 | 10.3 |

Small and hand-made (the question wording was tuned on it), so read it as a smoke test, not a benchmark.

## What it does

| Area | Tools | Backend |
|---|---|---|
| Wallet | `wallet_info`, `receive`, `send_sol`, `send_token`, `tx_status`, `airdrop` (devnet) | any Solana RPC, solders |
| Analyze | `token_audit`, `token_info`, `search_tokens`, `pool_info`, `rug_check`, `holders`, `trending`, `new_launches` | Dexscreener, RugCheck, RPC, Bubblemaps, PumpPortal |
| Trade | `quote`, `swap`, `pump_trade`, `buy_with_tpsl`, `positions_status`, `close_position` | Jupiter Swap v2, PumpPortal local tx (0.5% fee), positions manager |
| Scan | `scan_wallet` | RPC parsed transactions |
| Launch | `launch_token` (bonk keyless / pump needs Pinata JWT), `claim_creator_fees` | PumpPortal + IPFS |
| Memory | `remember`, `recall`, `trade_history` | SQLite (FTS5) |
| Signals | `signal_runners`, `signal_performance`, `signal_backtest`, `farm_scan`, `scanner_status` | signal ledger (SQLite), GeckoTerminal, Dexscreener, PumpPortal |
| Market | `trenches_pulse` (smallcap volume + Trench Fear & Greed) | GeckoTerminal, DefiLlama, Dune (optional) |
| Wiki | `wiki_search`, `wiki_read`, `wiki_note` | bundled markdown + `~/.heavymetal/wiki` |
| Keys | `connector_status` | Birdeye, Helius, Dune (optional keys) |

## Signals, farms, Trenches, wiki

**Farms get flagged like rugs.** `token_audit` runs Fair-style farm gates on every token: wash (24h volume > 300x liquidity),
zero-reserve pools, round-tripping (100+ swaps/wallet), fee/points farming (15+ swaps/wallet on a near-zero-fee pool),
thin crowds (< 25 wallets carrying $50K+) and flat loops. A hit is `HARD PASS / FARM`, and the swap review blocks the buy in
code (`FARM_BLOCK`). Thresholds live in `[signals]`; Birdeye / Helius keys sharpen wallet counts.

**Signal ledger.** Every audit (yours, the agent's, or the background scanner's) becomes a signal once: verdict, FDV,
liquidity and a frozen feature snapshot. Marks follow it for 14 days; milestones 2x–100x are logged once and never deleted
(>= $25K liquidity). `/signals perf` shows per-verdict hit rates within 24h / 72h / 7d counting only matured signals, with n
and *thin* flags; `/signals backtest` compares the audit rules, a logistic model and the base rate walk-forward, with
lookahead-leak guards. `/signals backfill` fills outcomes from GeckoTerminal hourly candles.

**Background scanner** (REPL, mainnet, on by default, `/scanner off`): PumpPortal launches + migrations and GeckoTerminal new
pools. A launch becomes a signal at $25K 24h volume and $5K liquidity. It audits in code (no LLM), alerts above the prompt
and never trades.

**Trenches** (`/trenches`): Solana smallcap volume (<= $200M FDV; majors, stables, tokenized stocks and farm pools dropped and
disclosed), top-5 tickers, pace, regime vs its own 90d/180d/1y history, launch hold/ceiling ladders from the day-1 close,
and the **Trench Fear & Greed** index (volume 1/3 and 3 more arms against fixed normals; momentum 1/3). Sources are tagged:
`dune` (full population, your saved query: `/trenches sql`), `gt` (GeckoTerminal top-200 sweep), `est` (DefiLlama × measured
share). Methodology adapted from [Fair's Trenches Pulse](https://fairfund.vc/trenches/).

**Wiki** (`/wiki`): pages on launchpads (pump.fun, PumpSwap, bonk.fun, Meteora, Moonshot), farm patterns, rug archetypes and
past rugs. `token_audit` returns matching `wiki_refs`; dead or rugged signals get an auto post-mortem in
`~/.heavymetal/wiki/cases/`. Case pages carry a `verify:` note: check figures against primary sources.

**Keys** (`/keys`): `/keys set dune | dune_query_id | birdeye | helius` (hidden input, stored in config.toml). The agent asks you
to run it when a feature needs a key; it never asks for keys in chat. Env: `DUNE_API_KEY`, `HM_DUNE_QUERY_ID`,
`BIRDEYE_API_KEY`, `HELIUS_API_KEY`.

All transactions are signed locally; the key never leaves the machine and is never sent to a model. External text is marked untrusted in every tool result.

## Architecture

```
 TUI (Textual fullscreen) · Web Browser (textual-serve) · REPL (prompt_toolkit)
        |
 Agent loop (DeepSeek: LLM -> tool calls -> results ...)
        |
 Tool registry ── irreversible swap? ──> Swap review (code facts + Jev decisions) ──> verdict
        |
 Adapters: RPC/tx · Jupiter · PumpPortal · Dexscreener · RugCheck · IPFS · GeckoTerminal · DefiLlama · Dune · Birdeye · Helius
        |                                       ^
        |               Background scanner (code-only audits, marks, Trenches refresh)
        |
 SQLite ~/.heavymetal: sessions + full messages · trades ledger · reviews · usage · knowledge
                       · signals + marks + milestones · trench days · launches · fear & greed days
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for component and sequence diagrams.

```
heavymetal/
  app.py agent.py review.py decide.py env.py memory.py config.py settings.py ui.py main.py
  commands_signals.py ui_signals.py   # /trenches /signals /scanner /wiki /keys + rich renderers, toolbar
  data/                           # geckoterminal, defillama, dune (+ Trenches SQL), birdeye, helius, connectors
  signals/                        # farm filter, code-only audit, ledger, performance, backtest, scanner
  trenches/                       # gates, pulse (sweep/bank/backfill), launches (ladders), fear_greed
  kb/wiki.py  wiki/               # wiki index/search + bundled pages (launchpads, farms, rugs, methodology)
  providers/                      # anthropic_provider.py (native Claude), openai_compat.py (OpenRouter/Ollama/vLLM, ZDR)
  solana/                         # rpc, nodes, tx (sign/partial-sign/land), jupiter, pumpportal, dexscreener,
                                  # rugcheck, ipfs, resolver, fake_check, positions
  tools/                          # registry (+ review gate) and the tools above
  tui/                            # Textual TUI + textual-serve web mode
  prompts/system.md
scripts/review_eval.py   tests/
```

## Config

`~/.heavymetal/config.toml` (chmod 600). Env vars `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `HM_RPC_URL`, `JUPITER_API_KEY`, `PINATA_JWT` override it; `HEAVYMETAL_HOME` moves the whole data directory.

```toml
[llm]
provider = "auto"        # auto | anthropic | openrouter | openai
base_url = "https://openrouter.ai/api/v1"
api_key = "sk-or-..."
zdr = true
agent_model = "deepseek/deepseek-v4-flash"
review_model = "typesafe/jev-1.13"
review_api = "auto"

[review]
mode = "gate"            # gate | advise | off
actions = ["swap", "pump_trade", "buy_with_tpsl", "close_position"]
on_error = "block"
require_research = true
max_liquidity_pct = 2.0

[solana]
rpc_url = "https://<your-quicknode-endpoint>"
cluster = "mainnet"

[trade]
slippage_pct = 10.0
priority_fee_sol = 0.0001

[keys]                   # optional data connectors (/keys set <name>)
dune = ""
dune_query_id = ""
birdeye = ""
helius = ""

[signals]
scanner = true           # background scanner in the REPL (mainnet)
min_volume_h24 = 25000   # launch -> signal gates
min_liquidity_usd = 5000
milestone_min_liq = 25000
wash_turnover = 300.0    # farm gates
feefarm_swaps_per_wallet = 15.0
roundtrip_swaps_per_wallet = 100.0
deny_mints = []          # excluded by hand
fg_volume_normal = 0.0   # 0 = built-in; /trenches calibrate [save]
```

Use a dedicated RPC: the public mainnet endpoint rate-limits calls like `getTokenLargestAccounts`.

## RPC nodes

Save several nodes and switch between them at any time:

```
» /rpc                                         # list saved nodes: latency, slot, cluster, active (●) / failover (↳)
» /rpc add quicknode https://xxx.solana-mainnet.quiknode.pro/<key>/
» /rpc use quicknode                           # or /rpc use <url>, which saves it automatically
» /rpc rm public      ·   /rpc fallback on|off
» switch to devnet                             # in chat: the agent can switch between SAVED nodes only
```

- The cluster of each node is detected from its genesis hash. Switching to a devnet node moves the whole agent to devnet; mainnet-only tools are disabled there.
- **Failover:** if the active node fails (connection error, HTTP 429/5xx, node unhealthy), calls move to the next saved node on the **same cluster** and stay there. A notice is printed. JSON-RPC errors such as a failed preflight are not retried on other nodes.
- API keys in node URLs are masked in all output.
- One-off overrides: `heavymetal --rpc <name|url>` or `--devnet` (not saved).
- The agent tool `switch_rpc` accepts only saved node names, never URLs. A URL planted in a token description can't redirect the wallet to a malicious node.

Saved in config as:

```toml
[solana]
rpc_url = "https://xxx.solana-mainnet.quiknode.pro/<key>/"
rpc_fallback = true

[solana.rpc_nodes.quicknode]
url = "https://xxx.solana-mainnet.quiknode.pro/<key>/"
cluster = "mainnet"

[solana.rpc_nodes.public]
url = "https://api.mainnet-beta.solana.com"
cluster = "mainnet"
```

## Tests

```bash
uv run pytest -q                       # offline: review logic, deciders, tx building/partial signing, parsers, TUI
uv run ruff check . && uv run ruff format --check .
OPENROUTER_API_KEY=... uv run python scripts/review_eval.py   # real (paid) model calls
```

Transfers (`send_sol`, `send_token` with recipient token-account creation) were verified against a local `solana-test-validator`. Jupiter/PumpPortal trades and launches spend real SOL on mainnet; test them with tiny amounts.

## Risks (read this)

- **Autonomous: no confirmation prompts.** The agent signs transactions on its own. It can lose money.
- **The review reduces risk, it doesn't remove it.** It's a model; it can be wrong. Sends and launches are not model-reviewed by default.
- **Prompt injection.** Token names, descriptions and memos are untrusted text written by strangers.
- **The private key is on disk** at `~/.heavymetal/wallet.json`. Anyone with that file controls the funds. Back it up.
- **TP/SL targets are not executed automatically.** They are tracked and flagged in `/positions`; a sell happens only when you or the agent close the position.
- **Fund it with small amounts only.** The wallet balance is your only spending limit.
- **Signals and Fear & Greed are analysis, not advice.** Multiples are valuation comparisons, not returns; small samples are marked thin. The default Fear & Greed normals are an initial calibration; re-measure them on your own ledger.
- Memecoins are extremely high risk; most go to zero. Not financial advice.

## Roadmap

- Social analysis: token socials, Telegram groups, website checks, pluggable X/Twitter backend
- Model review for sends/launches (config already supports it), more eval cases
- Automatic TP/SL execution (targets are tracked and flagged today; closing is agent- or user-initiated)
- Signals and Trenches in the Textual TUI (they are REPL-only today); EVM chains for Trenches
- Done: farm filter, signal ledger + performance + backtests, background scanner, Trenches + Fear & Greed, agent wiki
- Done in 0.0.1: Textual TUI, browser UI, position tracking with PnL

## Contributing

Issues and PRs are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md).

Found a vulnerability (key handling, swap-review bypass, prompt injection that moves funds)? **Do not open a public issue.** See [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) © 2026 Ossein ([@opensourcenjoyer](https://github.com/opensourcenjoyer)) and Aksultan ([@aksultanakn](https://github.com/aksultanakn))
