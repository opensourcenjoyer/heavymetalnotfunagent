---
title: Volume bots and fake traction
tags: farm, volume bot, trending, makers, creator fees, dexscreener
summary: Paid bots that add transactions and "makers" to push a fresh token onto trending lists.
---

# Volume bots

Volume-bot services sell packages of transactions and unique "makers" for a token. Creators buy them to reach
trending lists (DEX Screener, launchpad front pages, Telegram trackers) and, where creators earn a fee share, to
recycle part of the cost through creator fees.

**Tells**
- many tiny buys of near-identical size, evenly spaced in time
- makers count high, holders count flat
- buy ratio > 70% for hours with no price progress (bots buy, the dev or snipers sell into them)
- DEX Screener boosts purchased at the same time (`boosts` in the audit)

heavymetal's `buy_ratio_h1 > 0.65` is a positive in the verdict **only** when the farm gates pass and there are no
farm warnings; a strong buy ratio on a pool with heavy churn is a warning, not momentum.
