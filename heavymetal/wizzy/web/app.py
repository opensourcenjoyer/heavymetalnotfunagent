"""FastAPI app: /, /s/{slug}, /s/{slug}/full (paywalled), /og/{slug}.png, /healthz, /tg/webhook."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from heavymetal.wizzy import og, scrolls
from heavymetal.wizzy.web import pages

# Paywall hook (payments/x402.py installs one): async fn(ctx, request, scroll) -> Response | None.
# Returning None means "allowed"; a Response (e.g. HTTP 402) is sent instead of the full scroll.
Paywall = Any
WEB_HOOKS: list[Any] = []  # fn(app, ctx) adding routes or middleware (payments)


def create_app(ctx, *, bot=None, dp=None, paywall: Paywall = None) -> FastAPI:
    app = FastAPI(title="Wizzy", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ctx = ctx
    base = lambda: ctx.wcfg.base_url  # noqa: E731

    def paywall_on() -> bool:
        return paywall is not None and bool(ctx.wcfg.pay_to)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        rows = ctx.wdb.all("SELECT * FROM scrolls ORDER BY created_at DESC LIMIT 12")
        return pages.landing([scrolls.Scroll.from_row(r) for r in rows])

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True}

    @app.get("/s/{slug}", response_class=HTMLResponse)
    async def scroll(slug: str) -> Response:
        s = scrolls.get(ctx.wdb, slug)
        if s is None:
            return HTMLResponse(pages.layout("Lost in the mist", "<h1>That scroll is lost in the mist.</h1>"), 404)
        return HTMLResponse(
            pages.scroll_page(s, base_url=base(), full=False, price=s.price_usdc, paywall_on=paywall_on())
        )

    @app.get("/s/{slug}/full", response_class=HTMLResponse)
    async def scroll_full(slug: str, request: Request) -> Response:
        s = scrolls.get(ctx.wdb, slug)
        if s is None:
            return HTMLResponse(pages.layout("Lost in the mist", "<h1>That scroll is lost in the mist.</h1>"), 404)
        if s.paywalled and paywall_on():
            blocked = await paywall(ctx, request, s)
            if blocked is not None:
                return blocked
        resp = HTMLResponse(pages.scroll_page(s, base_url=base(), full=True, price=s.price_usdc, paywall_on=False))
        grant = getattr(request.state, "grant_cookie", None)
        if grant:
            resp.set_cookie(
                grant[0], grant[1], max_age=30 * 86400, httponly=True, secure=base().startswith("https"), samesite="lax"
            )
        return resp

    @app.get("/og/{slug}.png")
    async def og_image(slug: str) -> Response:
        s = scrolls.get(ctx.wdb, slug)
        if s is None:
            return Response(status_code=404)
        first = s.reading.split("\n")[0][:140]  # the free reading only, never the paid body
        return Response(
            og.render(s.title, s.omen, first), media_type="image/png", headers={"Cache-Control": "public, max-age=3600"}
        )

    @app.post("/tg/webhook")
    async def tg_webhook(request: Request) -> Response:
        if bot is None or dp is None:
            return Response(status_code=404)
        from heavymetal.wizzy.bots.tg import feed_webhook

        ok = await feed_webhook(
            bot,
            dp,
            ctx.cfg.keys.telegram_webhook_secret,
            request.headers.get("X-Telegram-Bot-Api-Secret-Token"),
            await request.json(),
        )
        return JSONResponse({"ok": ok}, status_code=200 if ok else 401)

    for hook in WEB_HOOKS:
        hook(app, ctx)
    return app
