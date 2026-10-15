# Wizzy

Wizzy is a small wizard bear who reads Solana tokens and wallets for traders and newcomers on Telegram, X and
the web. It lives inside the heavymetal package and reuses its data and analysis code, but it is **read-only**:
it never loads the agent wallet, never imports the trading tool registry and never gives the language model any
tools. Readings are built from facts computed in code; the model only phrases them.

## Run it

```bash
uv sync --extra wizzy                 # adds aiogram, tweepy, fastapi, x402, pillow, ...
wizzy migrate                         # creates ~/.heavymetal/wizzy.db
wizzy read BONK                       # a reading in the terminal (the bear waits while it works)
wizzy read <mint | pump.fun link | dexscreener link | wallet>
wizzy tarot <wallet>                  # three cards for a wallet
wizzy prophecy --dry-run              # candidate prophecy claims from live Trenches data
wizzy score --dry-run                 # this week's prophecy scoreboard
wizzy tg --polling                    # Telegram bot, local
wizzy serve                           # website + Telegram webhook + X poller + all workers
wizzy status                          # settings, 24h spend, counts, which keys are set
```

Without an Anthropic key every reading is built from a code template, so everything works offline from the model.

## Keys

Set them with heavymetal's `/keys set <name>` (hidden input) or environment variables:

| Key | Env var | Needed for |
|---|---|---|
| `llm.anthropic_key` | `ANTHROPIC_API_KEY` | model-written readings (otherwise templated) |
| `telegram_bot_token` | `TELEGRAM_BOT_TOKEN` | the Telegram bot |
| `telegram_webhook_secret` | `TELEGRAM_WEBHOOK_SECRET` | verifying webhook calls in `wizzy serve` |
| `x_bearer_token`, `x_api_key`, `x_api_secret`, `x_access_token`, `x_access_secret`, `x_user_id` | `X_*` | X mentions and replies |
| `quickchart_api_key` | `QUICKCHART_API_KEY` | optional, higher chart limits |
| `sentry_dsn` | `SENTRY_DSN` | optional error reporting |
| `birdeye`, `helius`, `dune` | as in heavymetal | optional: better OHLCV, wallet history, volume |

## Settings (`[wizzy]` in config.toml, or `WIZZY_<FIELD>` env vars)

The ones you will touch: `base_url` (public https URL), `tg_enabled`, `x_enabled`, `pay_to` (public address that
receives payments; its key never lives on the server), `x402_network` (devnet by default), `scroll_price_usdc`,
`inner_price_stars`, `inner_price_usdc`, `prophecy_channel`, `prophecy_hours_utc`, `daily_llm_budget_usd`,
`admin_tg_chat`, `writer_model` (default `claude-opus-5-5`), `writer_effort`. See `heavymetal/config.py:WizzyConfig`.

## What it does

- **Readings** (`/read`, any ticker/CA/link/wallet in a DM, @mentions in groups and on X): facts from the audit,
  RugCheck, the mint account, OHLCV and DefiLlama; a 2-5 sentence reading plus a full scroll at `/s/<slug>`.
- **Rug scrying** (`/scry <CA>`): a quick omen, no model call. cursed (fake, active freeze authority, critical
  RugCheck), hexed (farmed volume), murky, blessed. Established tokens such as USDC are never called cursed.
- **Apprentice mode** (`/learn`, `/lesson <topic>`, `/rank`): ten lessons with quizzes in
  `heavymetal/wiki/lessons/`. Ranks Apprentice, Adept, Conjurer, Sorcerer, Archmage come only from passed quizzes.
  Readings suggest the lesson that matches what they found.
- **Wallet tarot** (`/tarot <wallet>`): past, present and future cards picked by fixed rules from trade history and
  holdings; stable for a wallet for a UTC day.
- **Prophecies**: 2-4 a day at `prophecy_hours_utc`, each a measurable claim made in code with a frozen baseline
  (narrative volume share, top-5 ticker hold, Fear & Greed direction, smallcap volume direction). Graded only after
  maturing, with data stamped after the claim; missing data voids. A **Sunday scoreboard** names the wrong calls.
- **Spellbook** (`/watch`, `/watches`, `/unwatch`): owl alerts in Telegram when top holders move, liquidity drops,
  an authority changes or a wallet moves. Unlock alerts wait for a vesting data source (`spellbook/providers.py`).
- **Inner Circle** (`/inner`): Telegram Stars subscription in the bot, Solana Pay USDC on the web. Free full scrolls,
  higher limits, more watches and a **familiar** (`/familiar`): owl +5 watches, cat early prophecies, raven +5
  readings/hour, toad a private weekly digest. Familiars are off-chain badges.
- **Full scrolls** are paywalled with x402 (USDC on Solana) at `/pay/s/<slug>` when `pay_to` is set.

## Safety

- No keypair, no agent model, no reviewer, no trading clients in the reader env (`heavymetal/env.py:build_reader_env`).
  `tests/test_wizzy_isolation.py` fails if any Wizzy module imports the tool registry or the wallet.
- The output guard (`heavymetal/wizzy/guard.py`) rejects any number, address, link or $TICKER not present in the
  facts; two retries, then a code template. Creator-written names are cleaned, links removed, and never trusted.
- Buy/sell/send requests get a fixed refusal. Rate limits run before any model call; a daily budget switches to
  templated readings and alerts `admin_tg_chat`.
- X: replies only to mentions, once per user per thread, with per-user and daily caps and a random delay.
  Mark the account as automated in X settings.
- Payments: Stars charges and Solana Pay signatures are unique (no replays); Solana Pay accepts only finalized
  transactions that include the order reference and credit `pay_to` with enough mainnet USDC.

## Deploy (Fly.io)

```bash
fly launch --no-deploy --copy-config
fly volumes create wizzy_data --size 1
fly secrets set ANTHROPIC_API_KEY=... TELEGRAM_BOT_TOKEN=... TELEGRAM_WEBHOOK_SECRET=$(openssl rand -hex 24) \
  WIZZY_BASE_URL=https://wizzy-bot.fly.dev WIZZY_PAY_TO=<public address> HM_RPC_URL=<mainnet RPC>
fly deploy
fly ssh console -C "uv run --no-sync wizzy tg --set-webhook"
```

`wizzy serve` runs everything in one process; SQLite lives on the volume. Keep `x402_network` on devnet until a
devnet purchase works end to end, then switch to `solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp`.
