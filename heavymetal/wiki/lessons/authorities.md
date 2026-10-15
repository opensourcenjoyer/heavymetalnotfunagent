---
title: Mint and freeze authority
tags: lesson, mint authority, freeze authority, honeypot, safety
summary: Two keys a token creator can keep; both should usually be revoked.
order: 3
---
# Mint and freeze authority

Every Solana token has two optional admin keys:

- **Mint authority** can create new tokens out of thin air. If it is active, the supply can be inflated and
  your share diluted at any time.
- **Freeze authority** can freeze any holder's tokens so they can't be sold. An active freeze authority is how
  many **honeypots** work: you can buy, but you can never sell.

For memecoins both should be **revoked** (set to nobody). Regulated stablecoins such as USDC keep them on
purpose, which is normal for them and a red flag for a random new token.

```quiz
Q: What can an active freeze authority do?
- [x] Freeze holders' tokens so they can't sell
- [ ] Create new tokens
- [ ] Lock the liquidity pool

Q: Why is an active mint authority risky on a new memecoin?
- [ ] It makes trading slower
- [x] The creator can print more tokens and dilute holders
- [ ] It hides the holder list

Q: USDC keeps a freeze authority. Is that a red flag for USDC?
- [ ] Yes, it is a honeypot
- [x] No, regulated stablecoins keep it by design
- [ ] Only on weekends
```
