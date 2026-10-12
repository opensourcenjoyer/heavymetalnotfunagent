---
title: Solana launchpads overview
tags: launchpad, bonding curve, graduation, migration, pump.fun, bonk, meteora
summary: Bonding-curve launchpads sell a fixed curve of supply, then "graduate" the token to an AMM pool.
verify: fee levels and graduation thresholds change; check the launchpad's own docs before relying on numbers
---

# Launchpads overview

Most Solana memecoins start on a **bonding-curve launchpad**:

1. A creator mints a fixed supply (typically 1B tokens) with mint and freeze authority revoked by the launchpad program.
2. Buyers trade against a **bonding curve**: price is a function of how much supply has been sold. There is no LP to pull
   while the token is on the curve.
3. When the curve fills (a market-cap / SOL threshold), the token **graduates** (migrates): the raised SOL plus remaining
   supply seed an AMM pool, and the LP is burned or locked by the program.

## What this means for audits
- **On the curve**: no DexScreener pool yet, liquidity is the curve itself. RugCheck LP numbers are meaningless here.
  The main risks are the creator's own buys (dev bag), bundled buys in the launch block, and sniper wallets.
- **Just graduated**: the most violent period. Early buyers and snipers sell into the new pool. A token that does not
  hold its day-1 close is common; the hold ladder in Trenches measures exactly that.
- **Program-owned LP** (burned at migration) cannot be pulled, so classic liquidity pulls are rare on graduated
  launchpad tokens. The rug moves to supply: see [[rugs/dev-dump]] and [[rugs/bundled-supply]].
- **Launchpad != safe**: the launchpad guarantees the contract mechanics, not the holders.

## Venues
| Launchpad | Curve program | Graduates to |
|---|---|---|
| [[launchpads/pump-fun]] | pump.fun | [[launchpads/pumpswap]] (Raydium before March 2025) |
| [[launchpads/bonk-fun]] | Raydium LaunchLab | Raydium AMM / CPMM |
| [[launchpads/meteora-dbc]] | Meteora Dynamic Bonding Curve | Meteora DAMM pools |
| [[launchpads/moonshot]] | Moonshot | Raydium / Meteora |

PumpPortal (`new_launches`, the scanner) streams pump.fun and bonk launches.
