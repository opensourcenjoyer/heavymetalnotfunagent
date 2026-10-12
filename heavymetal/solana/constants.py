from solders.pubkey import Pubkey

LAMPORTS_PER_SOL = 1_000_000_000
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

SYSTEM_PROGRAM = Pubkey.from_string("11111111111111111111111111111111")
TOKEN_PROGRAM = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
TOKEN_2022_PROGRAM = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
ATA_PROGRAM = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")

BASE_FEE_LAMPORTS = 5_000
ATA_RENT_LAMPORTS = 2_039_280


def explorer_tx(sig: str, cluster: str = "mainnet") -> str:
    suffix = "" if cluster == "mainnet" else f"?cluster={cluster}"
    return f"https://solscan.io/tx/{sig}{suffix}"


def is_valid_pubkey(s: str) -> bool:
    try:
        Pubkey.from_string(s)
        return True
    except Exception:  # noqa: BLE001
        return False
