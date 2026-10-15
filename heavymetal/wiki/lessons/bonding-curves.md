---
title: Bonding curves and graduation
tags: lesson, bonding curve, pump.fun, launchpad, migration
summary: How launchpad tokens are priced before they get a real pool.
order: 10
---
# Bonding curves and graduation

Launchpads like pump.fun and bonk.fun sell new tokens on a **bonding curve**: a formula that raises the price
as more tokens are bought, with no separate liquidity pool yet.

- Early on, the curve itself is the market. The "holder" with the largest balance is often the curve.
- When enough SOL has gone in, the token **graduates** (migrates) to a real pool such as PumpSwap or Raydium.
- Most tokens never graduate. Graduation is not a guarantee either: many dump right after migrating.

```quiz
Q: What prices a token before it graduates?
- [x] The launchpad's bonding curve formula
- [ ] A Raydium pool
- [ ] The creator by hand

Q: A token just graduated to a real pool. Is it now safe?
- [ ] Yes, graduation means it passed an audit
- [x] No, many tokens dump after migrating
- [ ] Only if it has more than 10 holders
```
