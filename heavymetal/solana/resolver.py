"""Smart link and address resolver: extracts token mint or pair from URLs or raw base58 pubkeys."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from heavymetal.solana.constants import is_valid_pubkey

# Common base58 pattern (Solana addresses are 32-44 base58 chars)
BASE58_RE = re.compile(r"\b[1-9A-HJ-NP-za-km-z]{32,44}\b")


@dataclass
class ResolvedTarget:
    raw_input: str
    address: str
    kind: str  # "mint" | "pair" | "unknown"
    mint: str
    pair: str | None = None
    dex: str | None = None
    symbol: str | None = None
    name: str | None = None
    source_url: str | None = None

    def to_dict(self) -> dict:
        return {
            "raw_input": self.raw_input,
            "address": self.address,
            "kind": self.kind,
            "mint": self.mint,
            "pair": self.pair,
            "dex": self.dex,
            "symbol": self.symbol,
            "name": self.name,
            "source_url": self.source_url,
        }


def extract_address_from_text(text: str) -> tuple[str | None, str | None]:
    """Extract a Solana base58 address and optional source URL from raw text or URLs.
    Returns (address, source_url).
    """
    cleaned = text.strip()
    if not cleaned:
        return None, None

    # Check if input is a URL
    if cleaned.startswith(("http://", "https://")):
        source_url = cleaned
        parsed = urlsplit(cleaned)
        path_parts = [p for p in parsed.path.split("/") if p]
        # Check path parts from right to left for a valid pubkey
        for part in reversed(path_parts):
            # Sometimes address has query params or fragments stripped by urlsplit
            candidate = part.split("?")[0].split("#")[0]
            if is_valid_pubkey(candidate):
                return candidate, source_url
        # If not in path, check regex search in the entire URL
        match = BASE58_RE.search(cleaned)
        if match and is_valid_pubkey(match.group(0)):
            return match.group(0), source_url
        return None, source_url

    # Plain address or string containing an address
    match = BASE58_RE.search(cleaned)
    if match and is_valid_pubkey(match.group(0)):
        return match.group(0), None

    return None, None


async def resolve_target(env, target_text: str) -> ResolvedTarget:
    """Resolve a URL, ticker, or base58 address to a verified token mint.
    Disambiguates between pair/pool addresses and token mint addresses.
    """
    address, source_url = extract_address_from_text(target_text)
    if not address:
        raise ValueError(f"Could not extract a valid Solana address from '{target_text}'")

    # 1. First, check if this address is directly a token mint on-chain
    try:
        mint_info = await env.rpc.mint_info(address)
        if mint_info:
            # It's a token mint! Check if DexScreener has pairs for it to get metadata
            pairs = []
            try:
                pairs = await env.dex.token_pairs(address)
            except Exception:  # noqa: BLE001
                pass
            top_pair = pairs[0] if pairs else None
            return ResolvedTarget(
                raw_input=target_text,
                address=address,
                kind="mint",
                mint=address,
                pair=top_pair.get("pair") if top_pair else None,
                dex=top_pair.get("dex") if top_pair else None,
                symbol=top_pair["base"].get("symbol") if top_pair and top_pair.get("base") else None,
                name=top_pair["base"].get("name") if top_pair and top_pair.get("base") else None,
                source_url=source_url,
            )
    except Exception:  # noqa: BLE001
        pass

    # 2. If it wasn't directly a mint, check if it's a Pair address on DexScreener
    try:
        pair_data = await env.dex.pair(address)
        if pair_data and pair_data.get("base") and pair_data["base"].get("address"):
            base_mint = pair_data["base"]["address"]
            return ResolvedTarget(
                raw_input=target_text,
                address=address,
                kind="pair",
                mint=base_mint,
                pair=address,
                dex=pair_data.get("dex"),
                symbol=pair_data["base"].get("symbol"),
                name=pair_data["base"].get("name"),
                source_url=source_url,
            )
    except Exception:  # noqa: BLE001
        pass

    # 3. Fallback: treat as mint address
    return ResolvedTarget(
        raw_input=target_text,
        address=address,
        kind="unknown",
        mint=address,
        source_url=source_url,
    )
