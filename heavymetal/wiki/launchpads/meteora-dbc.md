---
title: Meteora (DBC, DLMM, DAMM)
tags: launchpad, meteora, dbc, dlmm, damm, single-sided liquidity, low fee
summary: Meteora's Dynamic Bonding Curve powers several launchpads; DLMM pools can run very low fees.
verify: Meteora products and fee schedules evolve; check docs.meteora.ag
---

# Meteora

- **DBC (Dynamic Bonding Curve)**: a configurable curve other launchpads build on (Believe and others in 2025).
  Graduates into Meteora **DAMM** pools.
- **DLMM**: concentrated, bin-based liquidity with dynamic fees. Pools can be created **single-sided** (only the new
  token deposited). A single-sided pool lets a creator "sell" supply into the pool as buyers arrive and then withdraw
  the SOL/USDC side. That mechanic is central to [[rugs/cases/libra-2025]].
- Low or dynamic fee tiers make DLMM pools a venue for [[farms/fee-farming]] (points or rebate farming), where the
  cost of churning volume is tiny.

## Audit notes
- For DLMM pools, "liquidity" may be mostly the token side. Check who added it and whether they can remove it:
  it is not burned like a launchpad migration.
- Single-sided liquidity owned by the deployer = they can pull the quote side at any time ([[rugs/liquidity-pull]]).
