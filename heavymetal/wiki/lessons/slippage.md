---
title: Slippage and price impact
tags: lesson, slippage, price impact, swaps
summary: Why the price you get differs from the price you saw.
order: 9
---
# Slippage and price impact

- **Price impact** is how much your own trade moves the price. Big trades in thin pools have big impact.
- **Slippage tolerance** is the maximum difference from the quoted price you accept before the swap fails.
- High slippage settings on thin pools invite **sandwich bots**, which buy just before you and sell just
  after, pocketing the difference.

Rule of thumb: compare your trade size to the pool's liquidity. A trade worth 2% of the pool already moves the
price noticeably.

```quiz
Q: What is price impact?
- [x] How much your own trade moves the price
- [ ] The fee charged by the DEX
- [ ] The time a swap takes

Q: Why can a very high slippage setting cost you money?
- [x] Bots can sandwich your trade within that tolerance
- [ ] It makes the transaction slower
- [ ] It locks your tokens
```
