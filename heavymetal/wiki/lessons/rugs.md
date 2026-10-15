---
title: How rugs happen
tags: lesson, rug pull, honeypot, dev dump, impersonation
summary: The common ways buyers lose everything, and what checks catch them.
order: 8
---
# How rugs happen

- **Liquidity pull**: the creator withdraws the pool. Check: LP burned or locked.
- **Honeypot**: you can buy but not sell (often an active freeze authority or a Token-2022 trap). Check:
  freeze authority revoked, no transfer hooks or permanent delegates.
- **Dev dump**: insiders hold a big share and sell into buyers. Check: holder concentration and bundles.
- **Impersonation**: a fake token copies a famous ticker. Check: the mint address, not the name.
- **Infinite mint**: an active mint authority prints new supply. Check: mint authority revoked.

No single check proves a token is safe. Wizzy's omen sums up several of them.

```quiz
Q: A token is named exactly like a famous one. What should you check?
- [x] Its mint address against the real one
- [ ] Its logo
- [ ] How many people talk about it

Q: Which check helps against a liquidity pull?
- [ ] Holder count
- [x] LP burned or locked
- [ ] Token age
```
