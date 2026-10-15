"""x402 micropayments for full scrolls (USDC on Solana, exact scheme) via the official x402 Python SDK.

/s/{slug}/full checks entitlements (paid-scroll cookie or Inner Circle). Without one it answers HTTP 402 with a
link to /pay/s/{slug}, which is the route protected by the x402 middleware (browser paywall UI included). The
middleware only calls our handler after the payment verifies; the handler records the purchase and sets the cookie.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from heavymetal.wizzy import scrolls
from heavymetal.wizzy.payments import entitlements as ent
from heavymetal.wizzy.web import pages

DEVNET = "solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1"
PAYMENT_HEADERS = ("PAYMENT-SIGNATURE", "X-PAYMENT")


def make_paywall(ctx):
    async def paywall(ctx_, request: Request, scroll):
        ok, grant = ent.scroll_access(ctx_.wdb, dict(request.cookies), dict(request.query_params), scroll.slug)
        if ok:
            if grant:
                request.state.grant_cookie = grant
            return None
        price = scroll.price_usdc or ctx_.wcfg.scroll_price_usdc
        body = (
            f"{pages.omen_badge(scroll.omen)}<h1>{pages.esc(scroll.title)}</h1>"
            f'<div class="card"><p>The full scroll costs ${price:.2f} USDC on Solana.</p>'
            f'<p><a class="btn" href="/pay/s/{pages.esc(scroll.slug)}">Pay with x402</a></p>'
            '<p class="dim">Inner Circle members read every scroll free: send /inner to Wizzy on Telegram.</p></div>'
        )
        return HTMLResponse(pages.layout("Unlock this scroll", body), status_code=402)

    return paywall


def build_middleware_args(ctx) -> dict:
    """routes/server/paywall_config for PaymentMiddlewareASGI."""
    from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption, PaywallConfig
    from x402.http.types import RouteConfig
    from x402.mechanisms.svm.exact import ExactSvmServerScheme
    from x402.server import x402ResourceServer

    w = ctx.wcfg
    server = x402ResourceServer(HTTPFacilitatorClient(FacilitatorConfig(url=w.facilitator_url)))
    server.register(w.x402_network, ExactSvmServerScheme())
    routes = {
        "GET /pay/s/:slug": RouteConfig(
            accepts=[
                PaymentOption(
                    scheme="exact", pay_to=w.pay_to, price=f"${w.scroll_price_usdc:.2f}", network=w.x402_network
                )
            ],
            description="A full Wizzy scroll",
            mime_type="text/html",
            service_name="Wizzy",
        )
    }
    paywall_cfg = PaywallConfig(app_name="Wizzy", testnet=w.x402_network == DEVNET)
    return {"routes": routes, "server": server, "paywall_config": paywall_cfg}


def install(app, ctx, middleware=None) -> None:
    """Web hook: add /pay/s/{slug} and the x402 middleware (only when a pay_to address is configured)."""
    if not ctx.wcfg.pay_to:
        return

    @app.get("/pay/s/{slug}", response_class=HTMLResponse)
    async def paid(slug: str, request: Request):
        s = scrolls.get(ctx.wdb, slug)
        if s is None:
            return HTMLResponse(pages.layout("Lost in the mist", "<h1>That scroll is lost in the mist.</h1>"), 404)
        header = next((request.headers[h] for h in PAYMENT_HEADERS if h in request.headers), "")
        if header:
            ent.record(
                ctx.wdb,
                user_id=None,
                method="x402",
                tx_key=ent.tx_key_for_header(header),
                amount=ctx.wcfg.scroll_price_usdc,
                slug=slug,
            )
        resp = HTMLResponse(
            pages.scroll_page(s, base_url=ctx.wcfg.base_url, full=True, price=s.price_usdc, paywall_on=False)
        )
        resp.set_cookie(
            ent.SCROLL_COOKIE_PREFIX + slug,
            ent.scroll_token(ctx.wdb, slug),
            max_age=30 * 86400,
            httponly=True,
            secure=ctx.wcfg.base_url.startswith("https"),
            samesite="lax",
        )
        return resp

    if middleware is None:
        from x402.http.middleware.fastapi import PaymentMiddlewareASGI

        app.add_middleware(PaymentMiddlewareASGI, **build_middleware_args(ctx))
    else:
        app.add_middleware(middleware)
