---
title: Freeze-authority honeypot
tags: rug, honeypot, freeze authority, cannot sell
summary: An active freeze authority can freeze your token account so you can buy but never sell.
---

# Freeze-authority honeypot

SPL tokens can keep a **freeze authority**. Whoever holds it can freeze any holder's token account. Honeypots let
buys through, then freeze buyers (or everyone but the deployer).

- Launchpad tokens revoke freeze authority by construction.
- heavymetal: active freeze authority = **HARD PASS / HONEYPOT** in `token_audit`, and **RISK_BLOCK** in the swap review.
- Exceptions exist (regulated stablecoins such as USDC keep a freeze authority), which is why canonical mints are
  checked separately.
