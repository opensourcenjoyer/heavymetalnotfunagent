"""Token launches on pump.fun / bonk via PumpPortal, and creator-fee claims."""

from __future__ import annotations

from solders.keypair import Keypair

from heavymetal.solana import ipfs
from heavymetal.solana.constants import LAMPORTS_PER_SOL, explorer_tx
from heavymetal.solana.tx import send_and_confirm, sign_external
from heavymetal.tools.registry import err, ok, tool


@tool(
    "launch_token",
    "Create a new memecoin on bonk.fun (pool='bonk', keyless) or pump.fun (pool='pump', needs "
    "a Pinata JWT) with an optional dev buy. Irreversible; costs SOL.",
    {
        "name": {"type": "string"},
        "symbol": {"type": "string"},
        "description": {"type": "string"},
        "image": {
            "type": "string",
            "description": "URL or a file name inside ~/.heavymetal/images; omitted = generated placeholder",
        },
        "twitter": {"type": "string"},
        "telegram": {"type": "string"},
        "website": {"type": "string"},
        "dev_buy_sol": {"type": "number", "default": 0.0},
        "pool": {"type": "string", "enum": ["bonk", "pump"], "default": "bonk"},
    },
    ["name", "symbol"],
    irreversible=True,
    mainnet_only=True,
)
async def launch_token(
    env,
    name: str,
    symbol: str,
    description: str = "",
    image: str | None = None,
    twitter: str = "",
    telegram: str = "",
    website: str = "",
    dev_buy_sol: float = 0.0,
    pool: str = "bonk",
):
    if pool not in ("bonk", "pump"):
        return err("pool must be bonk or pump")
    if not (1 <= len(symbol) <= 10 and 1 <= len(name) <= 32):
        return err("name 1-32 chars, symbol 1-10 chars")
    bal = await env.rpc.balance_sol(env.address)
    if bal < dev_buy_sol + 0.03:
        return err(f"need about {dev_buy_sol + 0.03:.3f} SOL (dev buy + rent/fees), have {bal}")
    try:
        img = await ipfs.load_image(env.http, image)
    except ipfs.ImageSourceError as e:
        return err(str(e))
    meta = {
        "name": name,
        "symbol": symbol,
        "description": description,
        **{k: v for k, v in (("twitter", twitter), ("telegram", telegram), ("website", website)) if v},
    }
    if pool == "bonk":
        uri = await ipfs.upload_bonk(env.http, img, meta)
    else:
        uri = await ipfs.upload_pinata(env.http, env.cfg.keys.pinata_jwt, img, {**meta, "showName": True})
    mint_kp = Keypair()
    raw = await env.pump.create_tx(
        env.address,
        str(mint_kp.pubkey()),
        name,
        symbol,
        uri,
        dev_buy_sol,
        env.cfg.trade.slippage_pct,
        env.cfg.trade.priority_fee_sol,
        pool,
    )
    res = await send_and_confirm(env.rpc, sign_external(raw, [mint_kp, env.kp]))
    mint = str(mint_kp.pubkey())
    env.db.add_trade(
        env.session_id, "launch_token", "launch", mint, dev_buy_sol, "SOL", None, {**res, "uri": uri, "pool": pool}
    )
    if res["status"] != "confirmed":
        return err(res.get("error") or res["status"], mint=mint, **res)
    link = f"https://pump.fun/coin/{mint}" if pool == "pump" else f"https://bonk.fun/token/{mint}"
    return ok(**res, mint=mint, metadata_uri=uri, page=link, explorer=explorer_tx(res["signature"]))


@tool(
    "claim_creator_fees",
    "Claim accumulated creator fees for tokens this wallet launched. Irreversible.",
    {
        "pool": {
            "type": "string",
            "enum": ["pump", "meteora-dbc"],
            "default": "pump",
            "description": "pump for pump.fun, meteora-dbc for bonk launches",
        },
        "mint": {"type": "string", "description": "required for meteora-dbc"},
    },
    irreversible=True,
    mainnet_only=True,
)
async def claim_creator_fees(env, pool: str = "pump", mint: str | None = None):
    before = await env.rpc.balance_lamports(env.address)
    raw = await env.pump.collect_fee_tx(env.address, env.cfg.trade.priority_fee_sol, pool, mint)
    res = await send_and_confirm(env.rpc, sign_external(raw, [env.kp]))
    env.db.add_trade(env.session_id, "claim_creator_fees", "claim", mint, None, "SOL", None, res)
    if res["status"] != "confirmed":
        return err(res.get("error") or res["status"], **res)
    after = await env.rpc.balance_lamports(env.address)
    return ok(**res, sol_change=(after - before) / LAMPORTS_PER_SOL, explorer=explorer_tx(res["signature"]))
