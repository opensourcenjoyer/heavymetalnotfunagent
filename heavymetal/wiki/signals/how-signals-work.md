---
title: How signals work
tags: signals, verdict, ledger, milestones, multiple, backtest, performance, honesty, scanner
summary: Verdicts, the signal ledger, multiples, milestones, performance per verdict and leak-safe backtests.
---

# How signals work

**A signal** is the first audit of a token: by `token_audit` (you or the agent) or by the background scanner.
It stores the verdict, FDV, liquidity, price and a frozen snapshot of the audit's features at that moment.

**Verdicts** (in order): FAKE, HONEYPOT, FARM, HIGH_RISK (all HARD PASS), HIGH_CONVICTION, SPECULATIVE.

**Multiple** = current FDV / FDV when the signal was written. A valuation comparison, not a price return and not
a past peak. A later audit updates `verdict_now` but never moves the start.

**Milestones** 2x/3x/5x/10x/20x/50x/100x: logged once, never deleted on a pullback, only with >= $25K liquidity.
On the first observation only the highest level reached is logged, labelled first-observed.

**States**: running (1h and 24h up), cooling (24h up, 1h flat/down), falling, dead, rugged.

**Performance** (`/signals perf`): per entry verdict, how many hit 2x within 24h / 72h / 7d, the median multiple,
and how many died or rugged. A window only counts signals old enough to have lived through it.

**Honesty rules**: every rate prints its n; n < 5 is *thin*; no data is *n/a*, never zero.

**Backtest** (`/signals backtest`): rules vs a logistic model vs base rate, walk-forward by time.
Leak guards: features must be stamped at signal time; labels only from milestones after the signal and inside the
horizon; only fully matured signals; one row per mint; scaling fit on train only; OHLCV backfill uses candles that
open after the signal, stamped at their close.

**Scanner**: PumpPortal launches + migrations and GeckoTerminal new pools; a launch becomes a signal once it trades
$25K in 24h with $5K+ liquidity. It audits in code only and never trades.
