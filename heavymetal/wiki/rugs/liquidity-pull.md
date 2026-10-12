---
title: Liquidity pull
tags: rug, liquidity, lp, pull, unlocked, single-sided, high risk
summary: The deployer withdraws the quote side of the pool; price goes to zero and nobody can sell.
---

# Liquidity pull

**Mechanism**: the creator seeds a pool and keeps the LP tokens (or owns a single-sided position). After buyers add
SOL/USDC, the creator withdraws, taking the quote side.

**Tells**: LP not burned/locked (RugCheck `lp_locked_pct` low), LP owned by the deployer, a pool created by hand
rather than by a launchpad migration, single-sided DLMM liquidity ([[launchpads/meteora-dbc]]).

**In the ledger**: a signal whose liquidity collapses below $1K from a healthy start is marked `rugged`.

**Defence**: prefer launchpad-migrated pools (program-burned LP) or LP locked > 80%. Treat RugCheck scores > 60 as
HARD PASS / HIGH RISK.
