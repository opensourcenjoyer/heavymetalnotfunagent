"""Trading: Jupiter (any token, best route) and PumpPortal (pump.fun / bonk / raydium pools)."""

from __future__ import annotations

from heavymetal.solana.constants import SOL_MINT, USDC_MINT, explorer_tx, is_valid_pubkey
from heavymetal.solana.tx import send_and_confirm, sign_external
from heavymetal.tools.registry import err, ok, tool
from heavymetal.tools.wallet import to_raw


def norm_mint(m: str) -> str:
    return SOL_MINT if m.strip().upper() in ("SOL", "WSOL") else m.strip()


def succeeded(res: dict) -> bool:
    """Tool results report success as 'success' (most tools) or 'confirmed' (signed transactions)."""
    return isinstance(res, dict) and res.get("status") in ("success", "confirmed")


async def sol_price_usd(env) -> float:
    """Live SOL/USD price: Jupiter price API, falling back to the deepest SOL-quoted Dexscreener pool."""
    try:
        p = (await env.jup.prices([SOL_MINT])).get(SOL_MINT)
        if p:
            return float(p)
    except Exception:  # noqa: BLE001 - fall through to Dexscreener
        pass
    pairs = await env.dex.token_pairs(USDC_MINT)
    rates = [x["sol_usd"] for x in pairs if x.get("sol_usd")]
    if not rates:
        raise RuntimeError("could not fetch the SOL/USD price")
    return float(rates[0])


# tool -> the argument that holds the SOL amount of a buy
SOL_AMOUNT_ARG = {"swap": "amount", "pump_trade": "amount", "buy_with_tpsl": "sol_amount"}
USD_DESC = "spend this many US dollars worth of SOL instead (e.g. 5 for '$5'); converted at the live SOL price in code"


async def usd_to_sol(env, name: str, args: dict) -> tuple[dict, dict]:
    """If a buy was sized in USD (`amount_usd`), convert it to SOL in code before review and signing.

    Returns (args with the SOL amount filled in, meta for the reviewer). Raises ValueError on bad input.
    """
    if name not in SOL_AMOUNT_ARG or args.get("amount_usd") is None:
        return args, {}
    args = dict(args)
    usd = float(args.pop("amount_usd"))
    if usd <= 0:
        raise ValueError("amount_usd must be > 0")
    if name == "swap" and norm_mint(args.get("input_mint", "")) != SOL_MINT:
        raise ValueError("amount_usd only works for buys paid in SOL (input_mint='SOL')")
    if name == "pump_trade":
        if args.get("action") != "buy":
            raise ValueError("amount_usd only works for buys")
        args["denominated_in_sol"] = True
    price = await sol_price_usd(env)
    args[SOL_AMOUNT_ARG[name]] = round(usd / price, 6)
    return args, {"requested_usd": usd, "sol_usd": round(price, 4)}


async def decimals_of(env, mint: str) -> int:
    return 9 if mint == SOL_MINT else (await env.rpc.mint_info(mint))["decimals"]


def describe_trade(tool_name: str, args: dict) -> dict:
    """Normalize swap/pump_trade args to {side, mint, amount, unit} for the ledger and the reviewer."""
    if tool_name == "pump_trade":
        sol = str(args.get("denominated_in_sol", args.get("action") == "buy")).lower() == "true"
        return {
            "side": args.get("action"),
            "mint": args.get("mint"),
            "amount": args.get("amount"),
            "unit": "SOL" if sol else "tokens",
        }
    if tool_name == "buy_with_tpsl":
        return {"side": "buy", "mint": args.get("mint"), "amount": args.get("sol_amount"), "unit": "SOL"}
    if tool_name == "close_position":
        return {"side": "sell", "mint": args.get("mint"), "amount": "100%", "unit": "tokens"}
    i, o = norm_mint(args.get("input_mint", "")), norm_mint(args.get("output_mint", ""))
    if i == SOL_MINT:
        return {"side": "buy", "mint": o, "amount": args.get("amount"), "unit": "SOL"}
    if o == SOL_MINT:
        return {"side": "sell", "mint": i, "amount": args.get("amount"), "unit": "tokens"}
    return {"side": "swap", "mint": o, "input_mint": i, "amount": args.get("amount"), "unit": "input tokens"}


@tool(
    "quote",
    "Price quote for swapping amount of input token into output token (Jupiter, no transaction). "
    "Use 'SOL' for native SOL.",
    {
        "input_mint": {"type": "string"},
        "output_mint": {"type": "string"},
        "amount": {"type": "number", "description": "input amount in UI units"},
    },
    ["input_mint", "output_mint", "amount"],
    mainnet_only=True,
)
async def quote(env, input_mint: str, output_mint: str, amount: float):
    i, o = norm_mint(input_mint), norm_mint(output_mint)
    di, do = await decimals_of(env, i), await decimals_of(env, o)
    q = await env.jup.order(i, o, to_raw(amount, di))
    out = int(q.get("outAmount") or 0) / 10**do
    return ok(
        input_mint=i,
        output_mint=o,
        in_amount=amount,
        out_amount=out,
        price_impact_pct=q.get("priceImpactPct"),
        router=q.get("router") or q.get("swapType"),
        fee_bps=q.get("feeBps"),
    )


@tool(
    "swap",
    "Swap tokens via Jupiter (best price across routers, managed landing). Buy a memecoin with "
    "input_mint='SOL'; sell with output_mint='SOL'. Falls back to PumpPortal for pump.fun/bonk tokens. "
    "Give either amount (input token units, e.g. SOL) or, for SOL buys sized in dollars, amount_usd. "
    "Irreversible; reviewed before signing.",
    {
        "input_mint": {"type": "string"},
        "output_mint": {"type": "string"},
        "amount": {"type": "number", "description": "input amount in UI units (SOL for buys)"},
        "amount_usd": {"type": "number", "description": USD_DESC},
        "slippage_bps": {"type": "integer", "description": "optional; default lets Jupiter optimise"},
    },
    ["input_mint", "output_mint"],
    irreversible=True,
    mainnet_only=True,
)
async def swap(
    env,
    input_mint: str,
    output_mint: str,
    amount: float | None = None,
    slippage_bps: int | None = None,
    amount_usd: float | None = None,
):
    if amount_usd is not None:  # normally converted by the registry before review; direct calls land here
        args, _ = await usd_to_sol(env, "swap", {"input_mint": input_mint, "amount_usd": amount_usd})
        amount = args["amount"]
    i, o = norm_mint(input_mint), norm_mint(output_mint)
    if not (is_valid_pubkey(i) and is_valid_pubkey(o)) or i == o:
        return err("invalid mints")
    if amount is None:
        return err("give amount (or amount_usd for SOL buys)")
    if amount <= 0:
        return err("amount must be > 0")
    d = describe_trade("swap", {"input_mint": i, "output_mint": o, "amount": amount})
    try:
        res = await env.jup.swap(env.kp, i, o, to_raw(amount, await decimals_of(env, i)), slippage_bps)
        res["venue"] = "jupiter"
    except Exception as jerr:  # noqa: BLE001
        if SOL_MINT not in (i, o):
            return err(f"jupiter: {jerr}")
        token = o if i == SOL_MINT else i
        res = await _pump(env, "buy" if i == SOL_MINT else "sell", token, amount, i == SOL_MINT, "auto", None)
        res["venue"] = "pumpportal (jupiter failed: " + str(jerr)[:120] + ")"
    env.db.add_trade(env.session_id, "swap", d["side"], d["mint"], amount, d["unit"], None, res)
    if res.get("status") != "confirmed":
        return err(res.get("error") or res.get("status", "failed"), **res)
    return ok(**res, explorer=explorer_tx(res["signature"]))


async def _pump(env, action, mint, amount, in_sol, pool, slippage_pct) -> dict:
    raw = await env.pump.trade_tx(
        env.address,
        action,
        mint,
        amount,
        in_sol,
        slippage_pct or env.cfg.trade.slippage_pct,
        env.cfg.trade.priority_fee_sol,
        pool,
    )
    return await send_and_confirm(env.rpc, sign_external(raw, [env.kp]))


@tool(
    "pump_trade",
    "Buy or sell a pump.fun / bonk / raydium token via PumpPortal (works on bonding curves "
    "before Jupiter indexes them). Sell amount may be a percentage string like '100%'. 0.5% fee. "
    "Irreversible; reviewed before signing.",
    {
        "action": {"type": "string", "enum": ["buy", "sell"]},
        "mint": {"type": "string"},
        "amount": {"type": ["number", "string"], "description": "SOL (buy) or tokens / '50%' (sell)"},
        "amount_usd": {"type": "number", "description": "buys only: " + USD_DESC},
        "denominated_in_sol": {"type": "boolean", "description": "true if amount is SOL (default: true for buy)"},
        "pool": {
            "type": "string",
            "enum": ["auto", "pump", "pump-amm", "raydium", "raydium-cpmm", "launchlab", "bonk"],
            "default": "auto",
        },
        "slippage_pct": {"type": "number"},
    },
    ["action", "mint"],
    irreversible=True,
    mainnet_only=True,
)
async def pump_trade(
    env,
    action: str,
    mint: str,
    amount=None,
    denominated_in_sol: bool | None = None,
    pool: str = "auto",
    slippage_pct: float | None = None,
    amount_usd: float | None = None,
):
    if action not in ("buy", "sell") or not is_valid_pubkey(mint):
        return err("action must be buy|sell and mint must be a valid address")
    if amount_usd is not None:
        args, _ = await usd_to_sol(env, "pump_trade", {"action": action, "amount_usd": amount_usd})
        amount, denominated_in_sol = args["amount"], True
    if amount is None:
        return err("give amount (or amount_usd for buys)")
    in_sol = (action == "buy") if denominated_in_sol is None else denominated_in_sol
    if isinstance(amount, str) and amount.endswith("%"):
        in_sol = False
    res = await _pump(env, action, mint, amount, in_sol, pool, slippage_pct)
    res["venue"] = f"pumpportal/{pool}"
    num = float(amount) if not (isinstance(amount, str) and amount.endswith("%")) else None
    env.db.add_trade(env.session_id, "pump_trade", action, mint, num, "SOL" if in_sol else str(amount), None, res)
    if res["status"] != "confirmed":
        return err(res.get("error") or res["status"], **res)
    return ok(**res, explorer=explorer_tx(res["signature"]))


@tool(
    "buy_with_tpsl",
    "Buy a memecoin token with SOL and automatically set up Take-Profit (TP multiple) "
    "and Stop-Loss (SL %) tracking in the local position manager. Size it with sol_amount or amount_usd.",
    {
        "mint": {"type": "string", "description": "token mint address"},
        "sol_amount": {"type": "number", "description": "amount of SOL to spend"},
        "amount_usd": {"type": "number", "description": USD_DESC},
        "tp_multiple": {"type": "number", "default": 2.0, "description": "take-profit multiple (e.g. 2.0 for 2x)"},
        "sl_pct": {"type": "number", "default": 30.0, "description": "stop-loss percentage (e.g. 30.0 for -30%)"},
        "slippage_bps": {"type": "integer", "description": "optional slippage tolerance in basis points"},
    },
    ["mint"],
    irreversible=True,
    mainnet_only=True,
)
async def buy_with_tpsl(
    env,
    mint: str,
    sol_amount: float | None = None,
    tp_multiple: float = 2.0,
    sl_pct: float = 30.0,
    slippage_bps: int | None = None,
    amount_usd: float | None = None,
):
    if amount_usd is not None:
        args, _ = await usd_to_sol(env, "buy_with_tpsl", {"amount_usd": amount_usd})
        sol_amount = args["sol_amount"]
    if sol_amount is None:
        return err("give sol_amount (or amount_usd)")
    from heavymetal.solana.positions import track_new_position
    from heavymetal.solana.resolver import resolve_target

    try:
        resolved = await resolve_target(env, mint)
        target_mint = resolved.mint
        symbol = resolved.symbol or "TOKEN"
    except Exception:  # noqa: BLE001
        target_mint = norm_mint(mint)
        symbol = "TOKEN"

    swap_res = await swap(env, "SOL", target_mint, sol_amount, slippage_bps)
    if not succeeded(swap_res):
        return swap_res

    # Record position
    pos_data = await track_new_position(
        env=env,
        mint=target_mint,
        symbol=symbol,
        sol_amount=sol_amount,
        tp_multiple=tp_multiple,
        sl_pct=sl_pct,
        notes=f"Bought via buy_with_tpsl (tx: {swap_res.get('signature')})",
    )
    return ok(swap=swap_res, position=pos_data)


@tool("positions_status", "Check all active open trading positions with live prices, PnL %, and TP/SL alerts.")
async def positions_status(env):
    from heavymetal.solana.positions import evaluate_open_positions

    positions = await evaluate_open_positions(env)
    return ok(open_count=len(positions), positions=positions)


@tool(
    "close_position",
    "Sell an open token position back to SOL and mark it closed in the position ledger.",
    {
        "mint": {"type": "string", "description": "token mint to sell and close"},
        "reason": {"type": "string", "default": "MANUAL", "description": "reason: TP | SL | MANUAL"},
    },
    ["mint"],
    irreversible=True,
    mainnet_only=True,
)
async def close_position(env, mint: str, reason: str = "MANUAL"):
    from heavymetal.solana.positions import get_current_token_price

    target_mint = norm_mint(mint)
    open_pos = env.db.open_positions(target_mint)
    if not open_pos:
        return err(f"no open position found for mint {target_mint}")

    pos = open_pos[0]
    # Sell 100% via pump_trade or swap
    try:
        sell_res = await pump_trade(env, "sell", target_mint, "100%", denominated_in_sol=False)
    except Exception as e:  # noqa: BLE001 - not a PumpPortal token: fall back to Jupiter
        sell_res = err(f"pumpportal: {e}")
    if not succeeded(sell_res):
        # Fall back to swap
        from heavymetal.tools.wallet import holdings

        h = await holdings(env, env.address)
        token_bal = next((t["amount"] for t in h["tokens"] if t["mint"] == target_mint), 0)
        if token_bal <= 0:
            return err("zero token balance found to sell")
        sell_res = await swap(env, target_mint, "SOL", token_bal)
        if not succeeded(sell_res):
            return sell_res

    # Record close in DB
    exit_price = await get_current_token_price(env, target_mint)
    entry_price = pos.get("entry_price_usd")
    pnl_pct = round(((exit_price - entry_price) / entry_price) * 100, 2) if exit_price and entry_price else None

    env.db.close_position(
        pos_id=pos["id"],
        status=f"CLOSED_{reason.upper()}",
        exit_price_usd=exit_price,
        exit_signature=sell_res.get("signature"),
        pnl_pct=pnl_pct,
    )
    return ok(closed_position=pos["id"], pnl_pct=pnl_pct, result=sell_res)
