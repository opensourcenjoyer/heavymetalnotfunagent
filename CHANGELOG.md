# Changelog

All notable changes to **heavymetalagent** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **Farm filter**: wash loops, zero-reserve pools, round-tripping, fee/points farming, thin crowds, flat loops and a manual deny list (`heavymetal/signals/farm.py`). Farms are flagged like rugs: `token_audit` returns `HARD PASS / FARM` and the swap review blocks buys in code (`FARM_BLOCK`).
- **Signal ledger**: every audit is recorded once (first call, frozen features), marked for 14 days, with 2x–100x milestones that are never deleted. `/signals runners | perf | backtest | backfill | farms | <id>` and the `signal_runners`, `signal_performance`, `signal_backtest`, `farm_scan` tools.
- **Backtests** with lookahead-leak guards: walk-forward by time, features stamped at the signal, labels only after it, matured signals only, train-only scaling. Rules vs logistic model vs base rate (AUC, precision, recall, lift).
- **Background scanner** (REPL, mainnet): PumpPortal launches/migrations and GeckoTerminal new pools, audited in code, alerts above the prompt, never trades. `/scanner on|off|mark`, `scanner_status`.
- **Trenches**: Solana smallcap volume with disclosed gate drops, top-5 tickers, pace, regime, daily ledger (`dune` / `gt` / `est` sources), launch hold/ceiling ladders and the Trench Fear & Greed index. `/trenches`, `/fg`, `trenches_pulse`, bottom toolbar.
- **Agent wiki**: bundled pages on launchpads, farm patterns, rug archetypes and past rugs; user notes and auto post-mortems in `~/.heavymetal/wiki`. `/wiki`, `wiki_search`, `wiki_read`, `wiki_note`; `token_audit` returns `wiki_refs`.
- **Data connectors**: GeckoTerminal, DefiLlama (keyless); Dune, Birdeye, Helius (optional keys via `/keys set`, hidden input). `connector_status` tool.
- Buys can be sized in dollars: `swap`, `pump_trade` and `buy_with_tpsl` accept `amount_usd` ("buy $5 of X"). The code converts it to SOL at the live SOL price (Jupiter, Dexscreener fallback) before review and signing.
- The reviewer gets the USD value of every buy and `pct_of_holdings` for sells. A buy worth more than 120% of the user's stated dollar amount is blocked in code (`CORRECT_PARAMS`).

### Fixed
- Token audit card crashed (and was silently skipped) when the pair had no dex id or 1h volume.
- `token_audit` counted "freeze/mint authority revoked" as positives when the on-chain lookup had failed.
- Dollar-sized buys and "sell all" no longer get `CORRECT_PARAMS` from the reviewer, which made the agent retry in a loop in `gate` mode.
- `buy_with_tpsl` now records the position: it compared the swap status with `"success"`, but confirmed swaps return `"confirmed"`. TP/SL tracking was never saved. `close_position` had the same bug.
- `token_audit` counts as research for the mint it resolves (it takes a link/`target`, not `mint`). Previously, buys after an audit hit `RESEARCH_FIRST`.
- `token_audit` crashed with `'>=' not supported between NoneType and int` on pools without a liquidity figure.
- REDUCE_SIZE on `buy_with_tpsl` set `amount` instead of `sol_amount`, which made the tool fail with bad arguments.
- Swap reviewer now works with only an Anthropic key: `claude-*` review models go through the Anthropic API, and the default Jev reviewer falls back to `claude-haiku-4-5` when no OpenRouter key is set (previously every swap failed closed with `REVIEW_UNAVAILABLE`).
- Setting only `ANTHROPIC_API_KEY` now selects a Claude agent model (previously the default OpenRouter model was used with no key).
- First-run wizard and `AnthropicProvider` default to `claude-sonnet-5-5` instead of the retired `claude-3-5-sonnet-latest`; removed retired/nonexistent Claude IDs from the model pickers.

## [0.0.1] - 2026-10-11

### Initial MVP Release

An autonomous, lightweight, open-source AI agent for Solana memecoins and token trading. Built from scratch with local transaction signing, dual AI provider support, automated risk reviews, and integrated position tracking.

### Added

#### 1. Core Architecture & Multi-Provider AI Engine
- **Async Agent Loop**: Single turn-based asynchronous loop with tool calling, context windowing, and `Ctrl+C` interrupt handling without exiting the process.
- **Native Anthropic Provider (`heavymetal/providers/anthropic_provider.py`)**:
  - Full native support for Anthropic Claude models (`claude-sonnet-5-5`, `claude-opus-5-5`, `claude-fable-5-1`, `claude-haiku-4-5`).
  - Automatic conversion between internal conversation format and Anthropic's Messages API (separating system prompts, converting tool schemas to `input_schema`, and handling `tool_use` / `tool_result` blocks).
  - Per-model token pricing estimation and streaming support.
- **OpenAI-Compatible & OpenRouter Provider (`heavymetal/providers/openai_compat.py`)**:
  - Direct integration with OpenRouter, local Ollama, or vLLM endpoints.
  - Zero Data Retention (ZDR) routing enforcement (`llm.zdr = true`) with automatic ZDR endpoint verification.
  - Primary default model: `deepseek/deepseek-v4-flash`.
- **Secondary Review Gate (`heavymetal/review.py` & `heavymetal/decide.py`)**:
  - Modeled after TypeSafe's narrow invoice-processing evaluation architecture.
  - Evaluates every proposed swap against code facts and structured questions: `user_requested`, `params_ok`, `manipulation`, `intended_repeat`, and `fake_or_copycat`.
  - Supports OpenRouter decisions API with `typesafe/jev-1.13` (~1s latency, calibrated probabilities) with chat fallback.
  - Fails closed on risk blocks, honeypots, or injection attempts.

#### 2. Isolated Agent Native Wallet
- **Dedicated Sandbox Keypair (`~/.heavymetal/wallet.json`)**:
  - Generates and stores a dedicated local keypair with `chmod 600` permissions.
  - Completely separated from the user's personal browser wallets (Phantom, Solflare, Backpack).
  - User funds only what they want the agent to trade (e.g., 0.1–0.5 SOL bankroll), providing a hard-capped blast radius.
- **Gas & Rent Exemption Buffer**:
  - Enforces a minimum `0.005 SOL` reserve (`SOL_RESERVE = 0.005`) on all buys to prevent on-chain `InsufficientFundsForRent` failures when creating Associated Token Accounts (ATAs).

#### 3. Token Analysis & Due Diligence Pipeline
- **Smart Link & Target Resolver (`heavymetal/solana/resolver.py`)**:
  - Automatically parses DexScreener URLs (`https://dexscreener.com/solana/<pair>`), pump.fun coin links (`https://pump.fun/coin/<mint>`), Birdeye links, and raw base58 public keys.
  - Distinguishes between liquidity pair accounts and underlying SPL token mint addresses.
- **Token Audit Tool (`token_audit`)**:
  - Consolidates market data, order flow momentum, contract security, and holder concentration into a single actionable call.
  - Fetches 5m and 1h trading volume, buy vs. sell transaction counts, and computes buy-pressure momentum percentage.
  - Generates direct one-click Bubblemaps links (`https://app.bubblemaps.io/sol/token/{mint}`) for visual cluster inspection.
  - Produces clear market verdicts: `HIGH CONVICTION (BULLISH)`, `SPECULATIVE`, or `HARD PASS / FAKE TOKEN`.

#### 4. Fake Token & Contract Trap Defense (`heavymetal/solana/fake_check.py`)
- **Unicode Homoglyph & Zero-Width Sanitization**:
  - Translates cross-alphabet Cyrillic and Greek lookalikes (`А` -> `A`, `О` -> `O`) using a dedicated confusable mapping.
  - Strips invisible zero-width spaces (`\u200B`, `\uFEFF`, etc.) to prevent spoofed ticker evasion.
- **Canonical Ticker Impersonation Check**:
  - Detects counterfeit tokens attempting to mimic major Solana assets (`SOL`, `USDC`, `BONK`, `WIF`, `JUP`, `RAY`, `POPCAT`, `TRUMP`, etc.) on non-canonical mint addresses.
- **Token-2022 Trap Detection**:
  - Identifies transfer fee extensions (transfer tax honeypots > 0%).
  - Detects malicious transfer hook contracts.
  - Detects permanent delegates (enabling developers to burn or seize tokens).
  - Checks for default frozen account states.
- **On-Chain Authority Verification**:
  - Verifies mint authority and freeze authority status directly on-chain.
  - Integrates RugCheck risk scoring and flags copycat indicators.

#### 5. Trading & Position Management with TP/SL
- **Trading Venues (`heavymetal/tools/trade.py`)**:
  - **Jupiter Swap v2**: Managed routing across Metis, JupiterZ RFQ, and AMMs with local transaction signing.
  - **PumpPortal Local Trading**: Fast execution for pump.fun and bonk.fun bonding curve tokens before DEX migration.
- **Position Tracking Engine (`heavymetal/solana/positions.py` & `heavymetal/memory.py`)**:
  - SQLite `positions` table tracking entry price, token quantity, SOL invested, Take-Profit targets, Stop-Loss targets, and lifecycle status (`OPEN`, `CLOSED_TP`, `CLOSED_SL`, `CLOSED_MANUAL`).
  - `buy_with_tpsl`: Executes buy orders and automatically registers TP multiples (e.g. 2.0x) and SL percentages (e.g. 30%).
  - `positions_status`: Computes live market valuation, current PnL %, and flags target triggers.
  - `close_position`: Sells open positions back to native SOL and marks them closed in the database.
  - Interactive `/positions` REPL command.

#### 6. Terminal User Interface & Web Mode
- **Terminal REPL**:
  - Streaming token rendering via `rich.live.Live` with full Markdown parsing (bullet points, bold highlights, code fences).
  - Live reasoning display (`🧠`) and compact post-turn tool execution traces.
  - Command autocompletion via `prompt_toolkit`.
- **Interactive `/settings` Editor (`heavymetal/settings.py`)**:
  - Interactive terminal configurator to switch models (including latest Claude 5.x/3.x and DeepSeek), update API keys, toggle review modes (`gate`, `advise`, `off`), and tune slippage/priority fees.
  - Non-interactive command shortcuts (e.g., `/settings model claude-sonnet-5-5`, `/settings anthropic sk-ant-...`).
- **Fullscreen Textual TUI (`heavymetal --tui`)**:
  - Cyber-themed terminal dashboard featuring:
    - Top Status HUD (`HeaderHUD`): Live wallet address, SOL balance, cluster badge, RPC node & latency.
    - Token Radar Card (`RadarCard`): Visual buy/sell momentum bars, contract safety grid, Bubblemaps link, and quick-buy buttons.
    - Trade Execution Card (`TradeCard`): Transaction signatures, fill details, and explorer links.
    - Live Positions Sidebar (`PositionsPane`): Active PnL cards with background price polling and instant sell buttons.
- **Rookie Web Mode (`heavymetal --web`)**:
  - Built-in `textual-serve` runner providing access to the TUI directly in a web browser on `http://localhost:8000`.

#### 7. Verification & Tests
- Comprehensive test suite comprising 59 unit and integration tests across:
  - `tests/test_anthropic.py`: Schema conversion, message formatting, cost calculation.
  - `tests/test_trading_workflow.py`: URL resolution, homoglyph normalization, fake checks, position math.
  - `tests/test_review.py`: Priority gate ordering, injection blocks, fake token blocks, size reductions.
  - `tests/test_rpc.py`: Node failover, cluster isolation, latency probing, URL masking.
  - `tests/test_settings.py`: Settings commands, key masking, model switching.
  - `tests/test_tui.py`: Widget rendering, formatting, and Textual pilot composition.
  - `tests/test_core.py` & `tests/test_decide.py`: Serialization, ATA calculation, decision parsing.

#### 8. Open-Source Packaging
- MIT `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, bug report template.
- Ruff lint/format configuration; codebase formatted.
- Fixed `heavymetal --web` spawning the TUI with an invalid `tui` argument.
- Architecture diagrams moved to Mermaid in `docs/ARCHITECTURE.md` (rendered natively by GitHub).

[Unreleased]: https://github.com/opensourcenjoyer/heavymetalnotfunagent/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/opensourcenjoyer/heavymetalnotfunagent/releases/tag/v0.0.1
