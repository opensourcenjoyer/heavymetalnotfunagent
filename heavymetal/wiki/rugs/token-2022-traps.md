---
title: Token-2022 traps
tags: rug, token-2022, transfer fee, transfer hook, permanent delegate, default frozen
summary: Token-2022 extensions that let a deployer tax, block or take tokens.
---

# Token-2022 traps

The Token-2022 program adds extensions. Several are legitimate for some assets and dangerous on a memecoin:

| extension | risk |
|---|---|
| transfer fee | a % of every transfer goes to the authority; can be raised later up to the max |
| transfer hook | a custom program runs on every transfer and can make sells fail |
| permanent delegate | an address that can transfer or burn tokens from **any** account |
| default account state = frozen | new accounts start frozen (honeypot by default) |

`inspect_token_safety` reads the mint's extensions; a non-zero transfer fee, a transfer hook, a permanent delegate
or a default-frozen state each make the token a trap (HARD PASS / FAKE TOKEN, FAKE_TOKEN_BLOCK on buys).
