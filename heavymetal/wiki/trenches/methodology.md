---
title: Trenches methodology
tags: trenches, smallcap, volume, fear and greed, regime, gates, dune, geckoterminal, defillama
summary: How smallcap volume, the launch ladders and the Trench Fear & Greed index are measured.
---

# Trenches methodology

Adapted from Fair's public Trenches Pulse methodology, Solana only.

**Smallcap volume**: every DEX pool except pairs whose both sides are majors/stables, tokens above $200M FDV,
tokenised equities (on the list *and* above $1), and wash/inorganic/farm pools. Every drop is disclosed with its
pool count and dollars. **Trench 24H** = smallcap minus the top-5 tickers. **Pace** = 6h volume x4 vs 24h.

**Sources**, never silently mixed:
- `dune`: every trade of the last complete UTC day (your saved query, `/trenches sql`)
- `gt`: GeckoTerminal's 200 most-traded pools, rolling 24h, read on each refresh
- `est`: DefiLlama chain volume x the median measured smallcap share (days before the ledger, gaps)

**Launch cohort**: launches <= 14 days old with $25K+ in 24h, at least a day old. Multiples from the day-1 close;
tops wick-proof (highest hourly close with >= $500 traded). Dead launches stay until they age out.

**Fear & Greed**: weighted mean of four 0–100 arms. Smallcap volume (1/3, fixed normal), volume momentum (1/3,
last 7d vs prior 7d), hold ladder (1/6, fixed normal, 3-day average), ceiling ladder (1/6, fixed normal). Bands:
<=25 extreme fear, <=45 fear, <=55 neutral, <=75 greed, else extreme greed. Withheld with fewer than 8 scored
launches; momentum sits out 10 days after a volume-definition change that moved the total > 10%.

**Regime**: today's smallcap volume as a percentile of its own last 90 / 180 / 365 days.
