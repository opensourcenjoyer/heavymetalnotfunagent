---
title: Wash loops
tags: farm, wash, loop, turnover, flat price, bot
summary: A bot buying and selling against itself through a thin pool; turnover hundreds of times liquidity.
---

# Wash loops

**What it looks like**
- 24h volume many hundreds of times the pool's liquidity (a $20K pool "doing" $8M)
- buys and sells near 50/50, often similar sizes, at a nearly flat price (flat_loop), or a smooth staircase
- few distinct wallets relative to the swap count
- the token sits on trending lists that rank by volume or transactions

**Why it exists**: to look alive (trending placement, screeners sorted by volume), to collect creator or LP fee
shares, or to farm exchange volume rewards. Some loops run for weeks: Fair's notes describe a BSC token printing
about $165M a day at a flat price, excluded by hand because every rule passed it.

**How heavymetal catches it**: `wash` (turnover > 300x) and `flat_loop` (turnover > 100x, |24h change| < 2%,
buy share 45–55%). When a loop slips through, add the mint to `signals.deny_mints`.

**What to do**: never buy on volume alone. Look at liquidity and wallets first. A farm's chart is drawn by the farmer.
