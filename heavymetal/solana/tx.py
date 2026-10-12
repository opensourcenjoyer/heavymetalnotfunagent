"""Transaction building, signing and landing.

- Our own txs (transfers): build ix -> compile MessageV0 -> sign.
- External txs (PumpPortal, Jupiter): deserialize -> sign only our slot(s) -> send.
  Partial signing keeps JupiterZ (RFQ) routes working: the market maker co-signs at /execute.
- Landing: send, re-broadcast every ~2s until confirmed, failed, or blockhash expired.
"""

from __future__ import annotations

import asyncio
import struct
import time

from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import MessageV0, to_bytes_versioned
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.system_program import TransferParams, transfer
from solders.transaction import VersionedTransaction

from heavymetal.solana.constants import ATA_PROGRAM, SYSTEM_PROGRAM, TOKEN_PROGRAM
from heavymetal.solana.rpc import RPC


class TxError(RuntimeError):
    pass


# ------------------------------------------------------------------ instructions
def ata_address(owner: Pubkey, mint: Pubkey, token_program: Pubkey = TOKEN_PROGRAM) -> Pubkey:
    return Pubkey.find_program_address([bytes(owner), bytes(token_program), bytes(mint)], ATA_PROGRAM)[0]


def ix_create_ata_idempotent(payer: Pubkey, owner: Pubkey, mint: Pubkey, token_program: Pubkey) -> Instruction:
    ata = ata_address(owner, mint, token_program)
    return Instruction(
        ATA_PROGRAM,
        bytes([1]),
        [
            AccountMeta(payer, True, True),
            AccountMeta(ata, False, True),
            AccountMeta(owner, False, False),
            AccountMeta(mint, False, False),
            AccountMeta(SYSTEM_PROGRAM, False, False),
            AccountMeta(token_program, False, False),
        ],
    )


def ix_transfer_checked(
    source: Pubkey, mint: Pubkey, dest: Pubkey, owner: Pubkey, amount: int, decimals: int, token_program: Pubkey
) -> Instruction:
    data = bytes([12]) + struct.pack("<Q", amount) + bytes([decimals])
    return Instruction(
        token_program,
        data,
        [
            AccountMeta(source, False, True),
            AccountMeta(mint, False, False),
            AccountMeta(dest, False, True),
            AccountMeta(owner, True, False),
        ],
    )


def ix_transfer_sol(src: Pubkey, dst: Pubkey, lamports: int) -> Instruction:
    return transfer(TransferParams(from_pubkey=src, to_pubkey=dst, lamports=lamports))


def priority_ixs(priority_fee_sol: float, cu_limit: int = 200_000) -> list[Instruction]:
    """Convert a total priority fee in SOL into a micro-lamports-per-CU price."""
    if priority_fee_sol <= 0:
        return []
    micro_per_cu = int(priority_fee_sol * 1e9 * 1e6 / cu_limit)
    return [set_compute_unit_limit(cu_limit), set_compute_unit_price(micro_per_cu)]


# ------------------------------------------------------------------ signing
def build_signed(payer: Keypair, ixs: list[Instruction], blockhash: str) -> VersionedTransaction:
    msg = MessageV0.try_compile(payer.pubkey(), ixs, [], Hash.from_string(blockhash))
    return VersionedTransaction(msg, [payer])


def sign_external(raw: bytes, signers: list[Keypair]) -> VersionedTransaction:
    """Sign a serialized tx from an API, filling only the signer slots we own."""
    tx = VersionedTransaction.from_bytes(raw)
    msg = tx.message
    n = msg.header.num_required_signatures
    keys = list(msg.account_keys)[:n]
    sigs = list(tx.signatures) + [Signature.default()] * (n - len(tx.signatures))
    payload = to_bytes_versioned(msg)
    signed_any = False
    for kp in signers:
        if kp.pubkey() in keys:
            sigs[keys.index(kp.pubkey())] = kp.sign_message(payload)
            signed_any = True
    if not signed_any:
        raise TxError("transaction does not require any of our signers")
    return VersionedTransaction.populate(msg, sigs)


# ------------------------------------------------------------------ landing
async def send_and_confirm(
    rpc: RPC, tx: VersionedTransaction, timeout_s: float = 75, skip_preflight: bool = False
) -> dict:
    """Returns {signature, status: confirmed|failed|expired|timeout, error?, slot?}."""
    raw = bytes(tx)
    sig = str(tx.signatures[0])
    try:
        await rpc.send_raw(raw, skip_preflight=skip_preflight)
    except Exception as e:  # noqa: BLE001 - preflight failure: tx never landed
        return {"signature": sig, "status": "failed", "error": f"preflight: {e}"}
    last_valid = None
    try:
        _, last_valid = await rpc.latest_blockhash()
        last_valid += 150  # generous: our tx used an older or equal blockhash
    except Exception:  # noqa: BLE001
        pass
    deadline = time.monotonic() + timeout_s
    last_send = time.monotonic()
    while time.monotonic() < deadline:
        await asyncio.sleep(1.5)
        st = await rpc.signature_status(sig)
        if st:
            if st.get("err"):
                return {"signature": sig, "status": "failed", "error": str(st["err"]), "slot": st.get("slot")}
            if st.get("confirmationStatus") in ("confirmed", "finalized"):
                return {"signature": sig, "status": "confirmed", "slot": st.get("slot")}
        if last_valid is not None:
            try:
                if await rpc.block_height() > last_valid:
                    return {"signature": sig, "status": "expired", "error": "blockhash expired before landing"}
            except Exception:  # noqa: BLE001
                pass
        if time.monotonic() - last_send > 2:
            try:
                await rpc.send_raw(raw, skip_preflight=True)
            except Exception:  # noqa: BLE001
                pass
            last_send = time.monotonic()
    return {"signature": sig, "status": "timeout", "error": "not confirmed in time; check tx_status later"}
