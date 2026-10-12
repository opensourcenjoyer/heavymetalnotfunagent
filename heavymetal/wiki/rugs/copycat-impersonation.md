---
title: Copycats and impersonation
tags: rug, fake, copycat, impersonation, homoglyph, ticker, canonical mint
summary: Tokens copying a known ticker or name, sometimes with lookalike Unicode letters.
---

# Copycats and impersonation

Within minutes of a token trending, copies appear with the same ticker, the same image, and sometimes lookalike
characters (Cyrillic `а` for Latin `a`, zero-width spaces). Buyers who search by ticker buy the wrong mint.

- heavymetal normalises tickers (homoglyphs, zero-width characters) and compares against canonical mints
  (SOL, USDC, BONK, WIF, JUP, ...). A mismatch = **HARD PASS / FAKE TOKEN** and **FAKE_TOKEN_BLOCK**.
- For new memes there is no canonical list: the original is usually the oldest pool with the most liquidity and
  holders. Always trade by mint address, never by ticker.
- Trenches merges same-ticker pools into one ticker, so copycats don't split or inflate the top-5.
