---
title: Inorganic volume (round-tripping, thin crowds)
tags: farm, inorganic, roundtrip, thin crowd, wallets, sybil
summary: Volume from too few wallets to be a crowd, or wallets round-tripping 100+ swaps a day.
---

# Inorganic volume

Two shapes:

1. **Round-tripping**: wallets average 100+ swaps a day. No human trades like that; even active bots on a real
   market rarely do across a whole token. Gate: `roundtrip`.
2. **Thin crowd**: fewer than 25 wallets carrying $50K+ of volume. Real attention brings wallets. Gate: `thin_crowd`.

Sybil farms split one actor across hundreds of wallets to dodge the thin-crowd gate; that is why the swaps-per-wallet
and turnover gates exist alongside it, and why Birdeye unique-wallet counts or Helius swap samples sharpen the read.

Related: [[farms/volume-bots]], [[rugs/bundled-supply]] (the same wallet clusters often bundle the launch).
