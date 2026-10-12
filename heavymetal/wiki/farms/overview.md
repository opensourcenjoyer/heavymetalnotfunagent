---
title: Farm patterns overview
tags: farm, wash, volume, inorganic, filter, gates
summary: Farms print volume that is not a market. heavymetal flags them like rugs and never buys them.
---

# Farms: volume that is not a market

A **farm** is a token or pool whose volume is produced by a few actors for a reason other than price discovery:
creator-fee extraction, exchange volume points, trending-list placement, or to bait buyers with a fake chart.
The price and volume of a farm are not information. That is why heavymetal treats farms like rugs:

- `token_audit` returns **HARD PASS / FARM**
- the swap review blocks buys in code (**FARM_BLOCK**), the model cannot override it
- the scanner records them (so the filter itself can be measured) but never alerts
- Trenches drops their volume and prints what it dropped, in pools and dollars

## Gates (cfg `[signals]`)
| gate | rule | page |
|---|---|---|
| wash | 24h volume > 300x liquidity | [[farms/wash-loops]] |
| zero_reserve | liquidity unreadable, > $10K per wallet | [[farms/zero-reserve-pools]] |
| roundtrip | 100+ swaps per wallet per day | [[farms/inorganic-volume]] |
| feefarm | 15+ swaps per wallet per day through a near-zero-fee pool | [[farms/fee-farming]] |
| thin_crowd | < 25 wallets carrying $50K+ | [[farms/inorganic-volume]] |
| flat_loop | turnover > 100x, flat price, 50/50 flow | [[farms/wash-loops]] |
| manual | deny list (`signals.deny_mints`) | |

Wallet counts come from Birdeye (unique wallets) or Helius (parsed swaps) when keyed, else GeckoTerminal
buyers + sellers, which double-counts two-way wallets and therefore errs toward *not* calling a farm.
Onchain, bots and people cannot be told apart; the gates measure behaviour, not identity.

## Limits
- A real mania can turn over 100x+ in a day. The 300x wash line is deliberately far out.
- Thresholds were taken from Fair's Trenches methodology and tuned on Solana sweeps; backtest them on your own ledger
  (`/signals perf` shows how FARM-flagged calls actually performed versus the rest).
