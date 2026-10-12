---
title: pump.fun
tags: launchpad, pump.fun, pump, bonding curve, graduation, creator fees
summary: The largest Solana memecoin launchpad; bonding curve then migration to PumpSwap.
verify: graduation threshold, fees and creator-reward rules have changed several times
---

# pump.fun

- **Mechanics**: fixed 1B supply, authorities revoked by the program, bonding curve priced in SOL. Mints usually end
  in `pump` (vanity suffix), which is a hint, not proof.
- **Graduation**: when the curve completes (historically around a ~$69K–$100K market cap, depending on SOL price and
  the version of the curve), liquidity migrates. Since March 2025 the default destination is
  [[launchpads/pumpswap]]; before that it was Raydium.
- **Creator fees**: creators earn a share of trading fees (claimable with `claim_creator_fees`). This creates
  incentives to churn volume on one's own token: see [[farms/volume-bots]].
- **Volume**: pump.fun produces thousands of launches a day; the overwhelming majority never graduate. Do not treat
  "it launched on pump.fun" as a signal.

## Patterns seen here
- Dev buys a large share in the create transaction, then sells after graduation ([[rugs/dev-dump]]).
- Bundled launches: many wallets buying in the same block as the create ([[rugs/bundled-supply]]).
- Copycat tickers of whatever is trending, minutes after the original ([[rugs/copycat-impersonation]]).
- Livestream / celebrity launches with large sniper concentration ([[rugs/cases/hawk-2024]] is a related pattern).

## What heavymetal checks
`token_audit` reads mint/freeze authority (should be revoked), holder concentration (bonding curve account is
usually the #1 holder before graduation, so read past it), buy/sell flow, and the farm gates.
