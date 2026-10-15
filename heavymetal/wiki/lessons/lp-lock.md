---
title: LP lock and burn
tags: lesson, lp, liquidity lock, rug pull
summary: Whether the pool's liquidity can be pulled out by whoever created it.
order: 4
---
# LP lock and burn

When a pool is created, the creator receives **LP tokens**: a receipt for the liquidity they deposited. Whoever
holds them can withdraw the pool, which crashes the price to zero. This is the classic **liquidity pull rug**.

- **Burned** LP tokens are gone forever, so that liquidity can never be withdrawn.
- **Locked** LP tokens sit in a time-lock contract until a date.
- A high locked/burned percentage (80%+) removes the easiest rug path. It does not stop insiders from dumping
  their tokens into the pool.

Pump.fun tokens that graduate to PumpSwap have their liquidity handled by the launchpad, not the creator.

```quiz
Q: What can the holder of unlocked LP tokens do?
- [x] Withdraw the pool's liquidity
- [ ] Freeze other holders
- [ ] Mint new tokens

Q: The LP is 100% burned. Is the token now safe?
- [ ] Yes, nothing bad can happen
- [x] The liquidity can't be pulled, but holders can still dump their tokens
- [ ] No, burning LP means the pool is empty
```
