"""Solana Pay checkout for the Inner Circle on the web (off-platform: Telegram requires Stars inside the bot).

Verification (all required): the order's reference key is in the transaction's accounts, the transaction is
finalized and succeeded, the mint is mainnet USDC, pay_to's USDC balance rose by at least the amount, and the
signature was never used before (UNIQUE in entitlements).
"""

from __future__ import annotations

import time
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from solders.keypair import Keypair

from heavymetal.wizzy.payments import entitlements as ent
from heavymetal.wizzy.web import pages

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
ORDER_TTL_S = 3600


def new_order(wdb, user_id: int, amount: float) -> str:
    reference = str(Keypair().pubkey())
    wdb._x(
        "INSERT INTO solana_pay_orders(reference, user_id, amount, created_at) VALUES(?,?,?,?)",
        (reference, user_id, amount, time.time()),
    )
    return reference


def pay_url(pay_to: str, amount: float, reference: str) -> str:
    return (
        f"solana:{pay_to}?amount={amount:g}&spl-token={USDC_MINT}&reference={reference}"
        f"&label={quote('Wizzy')}&message={quote('Inner Circle')}"
    )


def _keys(tx: dict) -> list[str]:
    keys = tx["transaction"]["message"]["accountKeys"]
    return [k["pubkey"] if isinstance(k, dict) else k for k in keys]


def usdc_received(tx: dict, owner: str) -> float:
    meta = tx.get("meta") or {}

    def total(side: str) -> float:
        return sum(
            float(b["uiTokenAmount"].get("uiAmountString") or 0)
            for b in meta.get(side) or []
            if b.get("mint") == USDC_MINT and b.get("owner") == owner
        )

    return round(total("postTokenBalances") - total("preTokenBalances"), 6)


def check_tx(tx: dict | None, *, reference: str, pay_to: str, amount: float) -> bool:
    if not tx or (tx.get("meta") or {}).get("err") is not None:
        return False
    if reference not in _keys(tx):
        return False
    return usdc_received(tx, pay_to) + 1e-9 >= amount


async def find_payment(rpc, *, reference: str, pay_to: str, amount: float) -> str | None:
    sigs = await rpc.call("getSignaturesForAddress", [reference, {"limit": 10, "commitment": "finalized"}])
    for s in sigs or []:
        if s.get("err") is not None:
            continue
        tx = await rpc.call(
            "getTransaction",
            [
                s["signature"],
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "finalized"},
            ],
        )
        if check_tx(tx, reference=reference, pay_to=pay_to, amount=amount):
            return s["signature"]
    return None


async def settle_order(ctx, reference: str) -> str:
    """'paid', 'open', 'expired' or 'unknown'. Grants the Inner Circle once, on the first verified payment."""
    o = ctx.wdb.one("SELECT * FROM solana_pay_orders WHERE reference=?", (reference,))
    if o is None:
        return "unknown"
    if o["status"] == "paid":
        return "paid"
    sig = await find_payment(ctx.env.rpc, reference=reference, pay_to=ctx.wcfg.pay_to, amount=o["amount"])
    if sig:
        if ent.grant_inner(
            ctx.wdb, o["user_id"], days=ctx.wcfg.inner_days, method="solanapay", tx_key=sig, amount=o["amount"]
        ):
            ctx.wdb._x("UPDATE solana_pay_orders SET status='paid', tx_sig=? WHERE reference=?", (sig, reference))
            return "paid"
        return "open"  # signature already used for another grant
    if time.time() - o["created_at"] > ORDER_TTL_S:
        ctx.wdb._x("UPDATE solana_pay_orders SET status='expired' WHERE reference=? AND status='open'", (reference,))
        return "expired"
    return "open"


POLL_JS = """<script>
async function poll(){const r=await fetch('/inner/status/%s');const j=await r.json();
document.getElementById('st').textContent=j.status;if(j.status==='paid'){location.href='/inner/login?k='+j.k}
else if(j.status==='open'){setTimeout(poll,5000)}}setTimeout(poll,5000)</script>"""


def install(app, ctx) -> None:
    """Web hook: /inner/pay, /inner/status/{reference}, /inner/login."""
    if not ctx.wcfg.pay_to:
        return

    @app.get("/inner/pay", response_class=HTMLResponse)
    async def pay(u: str = ""):
        uid = ent.user_from_token(ctx.wdb, u, "u")
        if uid is None:
            return HTMLResponse(pages.layout("Link expired", "<h1>This link has expired. Send /inner again.</h1>"), 400)
        amount = ctx.wcfg.inner_price_usdc
        ref = new_order(ctx.wdb, uid, amount)
        url = pay_url(ctx.wcfg.pay_to, amount, ref)
        body = (
            f"{pages.bear()}<h1>Join the Inner Circle</h1><div class=card>"
            f"<p>{ctx.wcfg.inner_days} days for {amount:g} USDC on Solana.</p>"
            f'<p><a class="btn" href="{pages.esc(url)}">Open in your Solana wallet</a></p>'
            f'<p class="dim">Payment request: <code>{pages.esc(url)}</code></p>'
            '<p>Status: <b id="st">waiting for a finalized payment…</b></p></div>' + POLL_JS % pages.esc(ref)
        )
        return pages.layout("Inner Circle", body)

    @app.get("/inner/status/{reference}")
    async def status(reference: str):
        st = await settle_order(ctx, reference)
        out = {"status": st}
        if st == "paid":
            o = ctx.wdb.one("SELECT user_id FROM solana_pay_orders WHERE reference=?", (reference,))
            out["k"] = ent.inner_token(ctx.wdb, o["user_id"], ctx.wcfg.inner_days)
        return JSONResponse(out)

    @app.get("/inner/login")
    async def login(request: Request, k: str = ""):
        resp = RedirectResponse("/", status_code=303)
        if ent.user_from_token(ctx.wdb, k, "i") is not None:
            resp.set_cookie(
                ent.INNER_COOKIE,
                k,
                max_age=ctx.wcfg.inner_days * 86400,
                httponly=True,
                secure=ctx.wcfg.base_url.startswith("https"),
                samesite="lax",
            )
        return resp
