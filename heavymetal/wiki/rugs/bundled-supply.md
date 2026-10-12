---
title: Bundled supply and snipers
tags: rug, bundle, bundled launch, sniper, jito, insiders, concentration, bubblemaps
summary: Many wallets buy in the launch block (bundled via Jito) and later sell together.
---

# Bundled supply

**Mechanism**: the creator (or a sniper group) sends a Jito bundle with the create transaction plus dozens of buys
from fresh wallets, so a large share of supply is captured before anyone else can trade. The wallets look
independent; Bubblemaps usually shows them funded from the same source.

**Tells**: top-10 holders > 40% (excluding the pool/curve), many holders with identical balances, wallets funded
minutes before launch from one address, a cluster on Bubblemaps.

**Defence**: open the Bubblemaps link from `token_audit`; read past the #1 holder (usually the pool or bonding
curve); treat high concentration plus fresh wallets as a dump waiting to happen. See [[rugs/cases/hawk-2024]].
