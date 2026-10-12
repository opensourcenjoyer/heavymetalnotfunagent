---
title: Fee and points farming
tags: farm, feefarm, points, rebates, low fee, dlmm, clmm, volume points
summary: Wallets churning 15+ swaps a day through near-zero-fee pools to farm exchange or protocol volume points.
---

# Fee / points farming

When an exchange, aggregator or protocol rewards **volume** (points, airdrops, rebates, leaderboard prizes), the
cheapest way to earn is to churn a pair through a pool with a near-zero fee tier (1–5 bps CLMM/DLMM pools).

**Signature**
- many swaps per wallet per day (15+), often round-trips of the same size
- a near-zero-fee venue (Orca/Raydium CLMM low tiers, Meteora DLMM with low dynamic fees, prop AMMs)
- volume that disappears the day the campaign ends

**Gate**: `feefarm` = swaps per wallet >= 15 and a low-fee venue (dex in the low-fee list, or a Dune `min_fee_tier`
<= 5 bps). With a Helius key heavymetal samples the pool's recent swaps and measures swaps per wallet directly;
it also flags one wallet doing > 30% of recent swaps.

The same churn on a normal-fee pool only warns: active traders and bots on a hot token can do 10–20 swaps a day.
