"""Deterministic fake token & contract trap detector:
- Unicode homoglyph & zero-width character sanitization
- Canonical ticker impersonation defense
- Token-2022 extension traps (transfer fees, transfer hooks, permanent delegates, default frozen)
- On-chain mint & freeze authority honeypot detection
- RugCheck copycat & scam indicators
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from heavymetal.solana.constants import TOKEN_2022_PROGRAM

# Canonical Solana tokens and their authentic mint addresses
CANONICAL_MINTS: dict[str, str] = {
    "SOL": "So11111111111111111111111111111111111111112",
    "WSOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "RENDER": "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof",
    "POPCAT": "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
    "TRUMP": "6p6xgHyF7AeQHyVaEcauTEXDixbZioFiIesxoGyupump",
    "PYTH": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
    "JTO": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
    "BOME": "ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74WD8",
    "MEW": "MEW1gQWJ3nEXg2qgERiKu7FAFj79PHvQVREQUzScPP5",
}

# Zero-width and hidden characters regex
ZERO_WIDTH_RE = re.compile(r"[\u200B\u200C\u200D\u200E\u200F\uFEFF\u00AD\u2060\u2061\u2062\u2063\u2064]")

# Common visual confusable homoglyphs (Cyrillic, Greek -> Latin ASCII)
HOMOGLYPH_MAP = {
    # Cyrillic lookalikes
    "А": "A",
    "В": "B",
    "С": "C",
    "Е": "E",
    "Н": "H",
    "І": "I",
    "Ј": "J",
    "К": "K",
    "М": "M",
    "О": "O",
    "Р": "P",
    "Ѕ": "S",
    "Т": "T",
    "Х": "X",
    "У": "Y",
    "а": "A",
    "с": "C",
    "е": "E",
    "о": "O",
    "р": "P",
    "ѕ": "S",
    "х": "X",
    "у": "Y",
    # Greek lookalikes
    "Α": "A",
    "Β": "B",
    "Ε": "E",
    "Ζ": "Z",
    "Η": "H",
    "Ι": "I",
    "Κ": "K",
    "Μ": "M",
    "Ν": "N",
    "Ο": "O",
    "Ρ": "P",
    "Τ": "T",
    "Υ": "Y",
    "Χ": "X",
    "α": "A",
    "ο": "O",
    "ν": "V",
}


def normalize_ticker(raw_symbol: str | None) -> str:
    """Strip zero-width characters, replace cross-alphabet homoglyphs, normalize unicode, and uppercase."""
    if not raw_symbol:
        return ""
    # Strip zero-width/hidden chars
    cleaned = ZERO_WIDTH_RE.sub("", str(raw_symbol))
    # Translate confusables
    mapped = "".join(HOMOGLYPH_MAP.get(ch, ch) for ch in cleaned)
    # Normalize unicode homoglyphs
    norm = unicodedata.normalize("NFKD", mapped)
    # Strip any remaining non-ASCII diacritics
    ascii_clean = norm.encode("ASCII", "ignore").decode("utf-8")
    return ascii_clean.strip().lstrip("$").strip().upper()


@dataclass
class FakeCheckResult:
    mint: str
    is_fake: bool
    verdict: str  # "SAFE" | "SUSPICIOUS" | "FAKE_BLOCKED"
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    canonical_spoof: bool = False
    transfer_fee_bps: int = 0
    has_transfer_hook: bool = False
    has_permanent_delegate: bool = False
    freeze_authority: str | None = None
    mint_authority: str | None = None
    is_token_2022: bool = False

    def to_dict(self) -> dict:
        return {
            "mint": self.mint,
            "is_fake": self.is_fake,
            "verdict": self.verdict,
            "reasons": self.reasons,
            "warnings": self.warnings,
            "canonical_spoof": self.canonical_spoof,
            "transfer_fee_bps": self.transfer_fee_bps,
            "has_transfer_hook": self.has_transfer_hook,
            "has_permanent_delegate": self.has_permanent_delegate,
            "freeze_authority": self.freeze_authority,
            "mint_authority": self.mint_authority,
            "is_token_2022": self.is_token_2022,
        }


async def inspect_token_safety(env, mint: str, raw_symbol: str | None = None) -> FakeCheckResult:
    """Run deterministic fast-path security and fake checks on a token mint."""
    reasons: list[str] = []
    warnings: list[str] = []
    canonical_spoof = False
    fee_bps = 0
    has_hook = False
    has_perm_delegate = False
    is_2022 = False
    freeze_auth = None
    mint_auth = None

    # 1. Canonical ticker impersonation check
    clean_sym = normalize_ticker(raw_symbol)
    if clean_sym in CANONICAL_MINTS:
        official_mint = CANONICAL_MINTS[clean_sym]
        if mint != official_mint:
            canonical_spoof = True
            reasons.append(f"Impersonating ${clean_sym}: unofficial mint {mint[:8]}… != official {official_mint[:8]}…")

    # 2. On-chain Account & Extension Inspection
    try:
        acc_info = await env.rpc.call("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
        v = acc_info.get("value") if acc_info else None
        if v and isinstance(v.get("data"), dict):
            owner_prog = v.get("owner", "")
            is_2022 = owner_prog == str(TOKEN_2022_PROGRAM)
            parsed = v["data"].get("parsed") or {}
            info = parsed.get("info") or {}

            freeze_auth = info.get("freezeAuthority")
            mint_auth = info.get("mintAuthority")

            if freeze_auth:
                reasons.append(f"Active freeze authority ({freeze_auth[:8]}…): token can be honeypot-frozen")
            if mint_auth:
                warnings.append(f"Active mint authority ({mint_auth[:8]}…): dev can mint infinite tokens")

            # Check Token-2022 extensions
            extensions = info.get("extensions") or []
            for ext in extensions:
                ext_type = ext.get("extension")
                state = ext.get("state") or {}

                if ext_type == "transferFeeConfig":
                    # Older or current fee config
                    config = state.get("newerTransferFee") or state.get("olderTransferFee") or {}
                    bps = int(config.get("transferFeeBasisPoints") or 0)
                    if bps > 0:
                        fee_bps = bps
                        reasons.append(f"Malicious Token-2022 transfer fee: {bps / 100:.2f}% transfer tax honeypot")

                elif ext_type == "transferHook":
                    has_hook = True
                    hook_prog = state.get("programId")
                    reasons.append(
                        f"Token-2022 transfer hook active (program {str(hook_prog)[:8]}…): can block transfers"
                    )

                elif ext_type == "permanentDelegate":
                    has_perm_delegate = True
                    delegate = state.get("delegate")
                    reasons.append(f"Permanent delegate active ({str(delegate)[:8]}…): dev can confiscate/burn tokens")

                elif ext_type == "defaultAccountState":
                    acc_state = state.get("accountState")
                    if acc_state == "frozen":
                        reasons.append("Token-2022 default account state is FROZEN: new token accounts start frozen")
    except Exception as e:  # noqa: BLE001
        warnings.append(f"On-chain account inspection error: {e}")

    # 3. RugCheck integration check
    try:
        summary = await env.rug.summary(mint)
        if summary and summary.get("risks"):
            for r in summary["risks"]:
                name = (r.get("name") or "").lower()
                lvl = (r.get("level") or "").lower()
                if "copycat" in name or "impersonat" in name:
                    canonical_spoof = True
                    reasons.append(f"RugCheck flag: {r.get('name')} ({r.get('description', '')})")
                elif "honeypot" in name:
                    reasons.append(f"RugCheck flag: {r.get('name')}")
                elif lvl == "danger":
                    reasons.append(f"RugCheck danger: {r.get('name')}")
                elif lvl == "warn":
                    warnings.append(f"RugCheck warn: {r.get('name')}")
    except Exception:  # noqa: BLE001
        pass

    # Verdict synthesis
    if reasons:
        verdict = "FAKE_BLOCKED"
        is_fake = True
    elif warnings:
        verdict = "SUSPICIOUS"
        is_fake = False
    else:
        verdict = "SAFE"
        is_fake = False

    return FakeCheckResult(
        mint=mint,
        is_fake=is_fake,
        verdict=verdict,
        reasons=reasons,
        warnings=warnings,
        canonical_spoof=canonical_spoof,
        transfer_fee_bps=fee_bps,
        has_transfer_hook=has_hook,
        has_permanent_delegate=has_perm_delegate,
        freeze_authority=freeze_auth,
        mint_authority=mint_auth,
        is_token_2022=is_2022,
    )
