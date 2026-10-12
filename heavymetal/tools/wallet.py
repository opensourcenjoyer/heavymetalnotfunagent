"""Wallet tools: balances, receive, send SOL/SPL, tx status, devnet airdrop."""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from solders.pubkey import Pubkey

from heavymetal.solana.constants import (
    ATA_RENT_LAMPORTS,
    BASE_FEE_LAMPORTS,
    LAMPORTS_PER_SOL,
    SOL_MINT,
    explorer_tx,
    is_valid_pubkey,
)
from heavymetal.solana.tx import (
    ata_address,
    build_signed,
    ix_create_ata_idempotent,
    ix_transfer_checked,
    ix_transfer_sol,
    priority_ixs,
    send_and_confirm,
)
from heavymetal.tools.registry import err, ok, tool


def to_raw(amount: float, decimals: int) -> int:
    return int((Decimal(str(amount)) * (10**decimals)).to_integral_value(rounding=ROUND_DOWN))


async def holdings(env, address: str) -> dict:
    sol = await env.rpc.balance_sol(address)
    tokens = await env.rpc.token_accounts(address)
    prices = {}
    if env.cluster == "mainnet":
        try:
            prices = await env.jup.prices([SOL_MINT] + [t["mint"] for t in tokens])
        except Exception:  # noqa: BLE001 - prices are best-effort
            prices = {}
    total = sol * prices.get(SOL_MINT, 0)
    rows = []
    for t in sorted(tokens, key=lambda t: -t["ui_amount"] * prices.get(t["mint"], 0)):
        usd = t["ui_amount"] * prices[t["mint"]] if t["mint"] in prices else None
        total += usd or 0
        rows.append(
            {
                "mint": t["mint"],
                "amount": t["ui_amount"],
                "decimals": t["decimals"],
                "usd": round(usd, 2) if usd is not None else None,
            }
        )
    return {
        "address": address,
        "sol": sol,
        "sol_usd_price": prices.get(SOL_MINT),
        "tokens": rows,
        "total_usd": round(total, 2) if prices else None,
    }


@tool("wallet_info", "The agent's own wallet: address, SOL balance, all SPL/Token-2022 holdings with USD values.")
async def wallet_info(env):
    return ok(cluster=env.cluster, **await holdings(env, env.address))


@tool("receive", "Address (and Solscan link) where the user can send SOL or tokens to top up the agent wallet.")
async def receive(env):
    return ok(
        address=env.address,
        cluster=env.cluster,
        explorer=f"https://solscan.io/account/{env.address}"
        + ("" if env.cluster == "mainnet" else f"?cluster={env.cluster}"),
    )


@tool(
    "send_sol",
    "Send SOL from the agent wallet to an address. Irreversible.",
    {
        "to": {"type": "string", "description": "recipient address"},
        "amount_sol": {"type": "number", "description": "SOL to send"},
    },
    ["to", "amount_sol"],
    irreversible=True,
)
async def send_sol(env, to: str, amount_sol: float):
    if not is_valid_pubkey(to):
        return err(f"invalid recipient address: {to}")
    if to == env.address:
        return err("recipient is the agent's own wallet")
    lamports = to_raw(amount_sol, 9)
    if lamports <= 0:
        return err("amount must be > 0")
    pf = env.cfg.trade.priority_fee_sol
    bal = await env.rpc.balance_lamports(env.address)
    need = lamports + BASE_FEE_LAMPORTS + int(pf * LAMPORTS_PER_SOL)
    if need > bal:
        return err(f"insufficient SOL: have {bal / LAMPORTS_PER_SOL}, need {need / LAMPORTS_PER_SOL} incl. fees")
    bh, _ = await env.rpc.latest_blockhash()
    tx = build_signed(
        env.kp, priority_ixs(pf, 1_000) + [ix_transfer_sol(env.kp.pubkey(), Pubkey.from_string(to), lamports)], bh
    )
    res = await send_and_confirm(env.rpc, tx)
    env.db.add_trade(env.session_id, "send_sol", "send", SOL_MINT, amount_sol, "SOL", to, res)
    if res["status"] != "confirmed":
        return err(res.get("error") or res["status"], **res)
    return ok(**res, sent_sol=amount_sol, to=to, explorer=explorer_tx(res["signature"], env.cluster))


@tool(
    "send_token",
    "Send an SPL or Token-2022 token to an address (creates their token account if needed). Irreversible.",
    {
        "mint": {"type": "string"},
        "to": {"type": "string"},
        "amount": {"type": "number", "description": "token amount in UI units"},
        "all": {"type": "boolean", "description": "send the entire balance (ignores amount)"},
    },
    ["mint", "to"],
    irreversible=True,
)
async def send_token(env, mint: str, to: str, amount: float = 0, all: bool = False):  # noqa: A002
    if not (is_valid_pubkey(mint) and is_valid_pubkey(to)):
        return err("invalid mint or recipient address")
    held = [t for t in await env.rpc.token_accounts(env.address) if t["mint"] == mint]
    if not held:
        return err(f"wallet holds no {mint}")
    src = max(held, key=lambda t: t["amount"])
    raw = src["amount"] if all else to_raw(amount, src["decimals"])
    if raw <= 0 or raw > src["amount"]:
        return err(f"amount must be > 0 and <= balance {src['ui_amount']}")
    program = Pubkey.from_string(src["program"])
    mint_pk, to_pk = Pubkey.from_string(mint), Pubkey.from_string(to)
    bal = await env.rpc.balance_lamports(env.address)
    if bal < BASE_FEE_LAMPORTS + ATA_RENT_LAMPORTS:
        return err("not enough SOL for fees and a possible recipient token account (~0.0021 SOL)")
    ixs = priority_ixs(env.cfg.trade.priority_fee_sol, 60_000) + [
        ix_create_ata_idempotent(env.kp.pubkey(), to_pk, mint_pk, program),
        ix_transfer_checked(
            Pubkey.from_string(src["account"]),
            mint_pk,
            ata_address(to_pk, mint_pk, program),
            env.kp.pubkey(),
            raw,
            src["decimals"],
            program,
        ),
    ]
    bh, _ = await env.rpc.latest_blockhash()
    res = await send_and_confirm(env.rpc, build_signed(env.kp, ixs, bh))
    ui = raw / 10 ** src["decimals"]
    env.db.add_trade(env.session_id, "send_token", "send", mint, ui, "token", to, res)
    if res["status"] != "confirmed":
        return err(res.get("error") or res["status"], **res)
    return ok(**res, sent=ui, mint=mint, to=to, explorer=explorer_tx(res["signature"], env.cluster))


@tool(
    "tx_status",
    "Check a transaction signature: confirmed/finalized/failed.",
    {"signature": {"type": "string"}},
    ["signature"],
)
async def tx_status(env, signature: str):
    st = await env.rpc.signature_status(signature)
    if not st:
        return ok(signature=signature, found=False)
    return ok(
        signature=signature,
        found=True,
        confirmation=st.get("confirmationStatus"),
        error=st.get("err"),
        slot=st.get("slot"),
        explorer=explorer_tx(signature, env.cluster),
    )


@tool(
    "airdrop", "Devnet only: request test SOL for the agent wallet.", {"amount_sol": {"type": "number"}}, ["amount_sol"]
)
async def airdrop(env, amount_sol: float = 1.0):
    if env.cluster != "devnet":
        return err("airdrop only works on devnet")
    sig = await env.rpc.airdrop(env.address, to_raw(min(amount_sol, 2), 9))
    return ok(signature=sig, explorer=explorer_tx(sig, "devnet"))
