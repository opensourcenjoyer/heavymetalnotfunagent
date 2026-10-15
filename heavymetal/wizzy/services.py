"""`wizzy serve`: one asyncio process running the website, Telegram webhook, job queue and background workers."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time

from heavymetal.wizzy import jobs
from heavymetal.wizzy.features import register_all
from heavymetal.worker import BackgroundWorker

log = logging.getLogger("wizzy")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": round(record.created, 3),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def setup_logging() -> None:
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    root = logging.getLogger("wizzy")
    root.handlers[:] = [h]
    root.setLevel(logging.INFO)


def setup_sentry(ctx) -> bool:
    dsn = ctx.cfg.keys.sentry_dsn
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        return False
    sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0, send_default_pii=False)
    return True


def spend_report(ctx, now: float | None = None) -> dict:
    now = now or time.time()
    day = ctx.wdb.spend_since(now - 86400)
    rows = ctx.wdb.all(
        "SELECT surface, COUNT(*) AS n, COALESCE(SUM(cost_usd), 0) AS c FROM requests WHERE created_at>=? "
        "GROUP BY surface",
        (now - 86400,),
    )
    return {
        "spend_24h": round(day, 4),
        "budget": ctx.wcfg.daily_llm_budget_usd,
        "by_surface": {r["surface"]: {"requests": r["n"], "cost": round(r["c"], 4)} for r in rows},
    }


class CostWorker(BackgroundWorker):
    """Hourly: log the 24h spend; once a day, alert the admin chat when it passes the budget."""

    name = "wizzy-cost"

    def __init__(self, ctx, svc=None):
        super().__init__(ctx.env)
        self.ctx = ctx

    def loops(self):
        return (self._loop,)

    def tick(self, now: float | None = None) -> bool:
        rep = spend_report(self.ctx, now)
        log.info("spend %s", json.dumps(rep))
        if rep["spend_24h"] < rep["budget"] or not self.ctx.wcfg.admin_tg_chat:
            return False
        day = time.strftime("%Y-%m-%d", time.gmtime(now or time.time()))
        text = (
            f"⚠ Wizzy spent ${rep['spend_24h']:.2f} in 24h (budget ${rep['budget']:.2f}). "
            "Readings are templated until spend falls under the budget."
        )
        return (
            jobs.enqueue(
                self.ctx.wdb,
                "tg_dm",
                {"chat_id": self.ctx.wcfg.admin_tg_chat, "text": text},
                dedupe_key=f"budget:{day}",
            )
            is not None
        )

    async def _loop(self) -> None:
        while True:
            self.tick()
            await asyncio.sleep(3600)


# Job handlers and workers registered by feature modules: kind -> async fn(ctx, services, payload)
JOB_HANDLERS: dict[str, object] = {}
WORKER_FACTORIES: list[object] = []  # fn(ctx, services) -> BackgroundWorker | None


class Services:
    def __init__(self, ctx):
        self.ctx = ctx
        self.bot = None
        self.dp = None
        self.x = None
        self.workers: list = []

    def build(self):
        from heavymetal.wizzy.bots import x as xmod
        from heavymetal.wizzy.web.app import create_app

        register_all()
        keys = self.ctx.cfg.keys
        if self.ctx.wcfg.tg_enabled and keys.telegram_bot_token:
            from heavymetal.wizzy.bots import tg

            self.bot, self.dp = tg.build(self.ctx)
        if self.ctx.wcfg.x_enabled and xmod.x_ready(keys):
            self.x = xmod.XClient(keys)
        handlers = {"x_reply": lambda p: xmod.handle_reply_job(self.ctx, self.x, p)}
        handlers.update({k: (lambda p, fn=fn: fn(self.ctx, self, p)) for k, fn in JOB_HANDLERS.items()})
        self.workers.append(jobs.JobWorker(self.ctx.env, self.ctx.wdb, handlers))
        if self.x is not None:
            self.workers.append(xmod.XPoller(self.ctx, self.x))
        self.workers.append(CostWorker(self.ctx, self))
        for factory in WORKER_FACTORIES:
            w = factory(self.ctx, self)
            if w is not None:
                self.workers.append(w)
        return create_app(self.ctx, bot=self.bot, dp=self.dp, paywall=self.paywall())

    def paywall(self):
        try:
            from heavymetal.wizzy.payments.x402 import make_paywall
        except ImportError:
            return None
        return make_paywall(self.ctx)

    def status(self) -> list[str]:
        out = [f"web: {self.ctx.wcfg.base_url}"]
        out.append("telegram: webhook /tg/webhook" if self.bot else "telegram: off (no token or tg_enabled=false)")
        out.append("x: polling mentions" if self.x else "x: off (x_enabled=false or keys missing)")
        out += [f"worker: {w.name}" for w in self.workers]
        return out


async def serve(ctx) -> None:
    import uvicorn

    setup_logging()
    if setup_sentry(ctx):
        log.info("sentry enabled")
    svc = Services(ctx)
    app = svc.build()
    for w in svc.workers:
        if not w.start():
            log.warning("worker %s not started: %s", w.name, w.last_error)
    for line in svc.status():
        print(line)
    server = uvicorn.Server(uvicorn.Config(app, host=ctx.wcfg.host, port=ctx.wcfg.port, log_level="info"))
    try:
        await server.serve()
    finally:
        for w in svc.workers:
            with contextlib.suppress(Exception):
                await w.stop()
        if svc.bot is not None:
            await svc.bot.session.close()


async def set_webhook(ctx) -> str:
    from heavymetal.wizzy.bots import tg

    secret = ctx.cfg.keys.telegram_webhook_secret
    if not secret:
        raise RuntimeError("set telegram_webhook_secret first (/keys set telegram_webhook_secret)")
    url = f"{ctx.wcfg.base_url.rstrip('/')}/tg/webhook"
    if not url.startswith("https://"):
        raise RuntimeError(f"Telegram needs an https base_url, got {url}")
    bot, _ = tg.build(ctx)
    try:
        await bot.set_webhook(
            url, secret_token=secret, allowed_updates=["message", "callback_query", "pre_checkout_query"]
        )
    finally:
        await bot.session.close()
    return url


async def run_forever(*workers) -> None:  # pragma: no cover - helper for ad-hoc scripts
    for w in workers:
        w.start()
    await asyncio.Event().wait()
