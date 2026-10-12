---
title: PumpSwap
tags: launchpad, pumpswap, pump-amm, amm, graduation, zero reserve, farm
summary: pump.fun's own AMM, destination for graduated pump.fun tokens since March 2025.
verify: fee split between LPs, protocol and creators is set by pump.fun and has changed
---

# PumpSwap (pump-amm)

- Constant-product AMM run by pump.fun. Graduated pump.fun tokens migrate here; the migration LP is not pullable by the creator.
- Anyone can also create PumpSwap pools directly, including pools with **almost no reserves**.
- Trading fees include a creator share, so trading volume pays the creator.

## Farm risk
PumpSwap is where most zero-reserve farm pools show up in sweeps: pools with near-empty reserves printing large
"volume" from bots trading against themselves. On one day in 2026 the GeckoTerminal top-200 Solana sweep had
well over half its slots taken by such pools (Fair's Trenches notes report 145 of 199). That is why Trenches drops
pools with turnover > 300x liquidity and unreadable reserves: see [[farms/zero-reserve-pools]] and [[farms/wash-loops]].

## Reading a PumpSwap pair
- Compare 24h volume to liquidity. A healthy fresh launch can turn over 10–50x in a day; 300x is a loop.
- Check buyers vs sellers and swaps per wallet (GeckoTerminal gives buyers/sellers per window).
- A pool with a fresh launch, $5K liquidity and $3M of volume is not a runner: it is a farm.
