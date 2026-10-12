---
title: Zero-reserve pools
tags: farm, zero reserve, pumpswap, empty pool, liquidity, sweep
summary: Pools with empty or unreadable reserves that still print big volume; they flood volume rankings.
---

# Zero-reserve pools

Pools whose reserves are near zero (or that indexers cannot price) but that report large volume. Volume through
an empty book is not tradeable size: any real order would move the price to nothing.

- Common on permissionless AMMs where anyone can create a pool ([[launchpads/pumpswap]]).
- They crowd volume-sorted APIs. A top-200 sweep can lose most of its slots to them; a daily total read off such a
  sweep can swing tens of percent for no market reason. Trenches therefore never mixes numbers from different
  instruments (Dune full population vs GeckoTerminal sweep) in one delta.

**Gate**: liquidity unreadable or < $1 and more than $10K traded per wallet -> `zero_reserve`.
Without a wallet count the pool only gets a warning ("volume unverifiable").
