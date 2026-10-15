"""Payments: x402 full scrolls, Telegram Stars and Solana Pay for the Inner Circle. Wizzy never holds keys."""


def register() -> None:
    from heavymetal.wizzy.bots import tg
    from heavymetal.wizzy.payments import solana_pay, stars, x402
    from heavymetal.wizzy.web import app

    tg.ROUTER_HOOKS.append(stars.tg_hook)
    tg.EXTRA_HELP.append("\n/inner · join the Inner Circle")
    app.WEB_HOOKS.extend([x402.install, solana_pay.install])
