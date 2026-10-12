---
title: Rug archetypes
tags: rug, scam, overview, checklist, honeypot, liquidity, dev dump
summary: The ways memecoins rug, and the check that catches each one before a buy.
---

# Rug archetypes

| archetype | how it takes your money | caught by |
|---|---|---|
| [[rugs/liquidity-pull]] | deployer removes the pool's SOL/USDC side | LP locked/burned %, who owns the LP, RugCheck |
| [[rugs/dev-dump]] | creator / team sells a large bag into buyers | holder concentration, creator wallet, `scan_wallet` |
| [[rugs/bundled-supply]] | many wallets buy in the launch block, then dump together | top-10 %, Bubblemaps clusters |
| [[rugs/freeze-honeypot]] | freeze authority stops you from selling | freeze authority must be revoked (HARD PASS) |
| [[rugs/token-2022-traps]] | transfer fees, hooks, permanent delegate | Token-2022 extension scan (HARD PASS) |
| [[rugs/mint-authority]] | new supply minted and sold | mint authority must be revoked |
| [[rugs/copycat-impersonation]] | fake ticker of a known token | canonical-mint check, homoglyph scan |
| farms ([[farms/overview]]) | fake volume baits buyers | farm gates (HARD PASS / FARM) |

## Before any buy
1. `token_audit` (resolves the link, runs every check above, records the signal)
2. read the verdict: any **HARD PASS** is a no
3. for SPECULATIVE: look at holders past the pool/curve account, at the creator wallet, and at liquidity vs size
4. size so the buy is < 2% of pool liquidity (the review gate enforces this)

Past cases: [[rugs/cases/libra-2025]] (single-sided liquidity withdrawn by insiders),
[[rugs/cases/hawk-2024]] (sniper/insider supply concentration on a celebrity launch).
Auto post-mortems of your own dead signals appear under `cases/auto-*`.
