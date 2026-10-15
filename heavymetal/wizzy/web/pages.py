"""HTML for the scroll site. Markdown is rendered with raw HTML disabled; all text is escaped."""

from __future__ import annotations

import html
import re

from markdown_it import MarkdownIt

from heavymetal import mascot
from heavymetal.wizzy.charts import OMEN_COLOR

_md = MarkdownIt("commonmark", {"html": False, "linkify": False})

CSS = """
:root{--bg:#1a1426;--card:#241c35;--ink:#e9e4f0;--dim:#b8b0c8;--accent:#c77dff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.6 system-ui,sans-serif}
main{max-width:760px;margin:0 auto;padding:32px 20px 64px}a{color:var(--accent)}
.card{background:var(--card);border-radius:14px;padding:22px 24px;margin:18px 0}
.omen{display:inline-block;padding:2px 12px;border-radius:999px;font-weight:700;color:#1a1426}
h1{font-size:30px;line-height:1.2;margin:10px 0}h2{font-size:20px;margin-top:26px;color:var(--accent)}
pre.bear{color:var(--dim);font-size:11px;line-height:1.05;overflow:auto}
.dim{color:var(--dim);font-size:14px}.btn{display:inline-block;background:var(--accent);color:#1a1426;
padding:10px 18px;border-radius:10px;font-weight:700;text-decoration:none}img.chart{width:100%;border-radius:10px}
ul{padding-left:22px}footer{margin-top:40px;color:var(--dim);font-size:13px}
"""


def esc(s: str | None) -> str:
    return html.escape(s or "")


def md(s: str) -> str:
    return _md.render(s or "")


def section(body_md: str, name: str) -> str:
    """One '## name' section of a scroll body (used for the free preview)."""
    m = re.search(rf"^##\s+{re.escape(name)}\s*$(.*?)(?=^##\s|\Z)", body_md or "", re.M | re.S)
    return f"## {name}\n{m.group(1).strip()}" if m else ""


def layout(title: str, body: str, *, og_image: str | None = None, url: str | None = None, desc: str = "") -> str:
    meta = [
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(desc[:200])}">',
        '<meta name="twitter:card" content="summary_large_image">',
    ]
    if og_image:
        meta.append(f'<meta property="og:image" content="{esc(og_image)}">')
        meta.append(f'<meta name="twitter:image" content="{esc(og_image)}">')
    if url:
        meta.append(f'<meta property="og:url" content="{esc(url)}">')
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{esc(title)}</title>{''.join(meta)}<style>{CSS}</style></head><body><main>{body}"
        "<footer>Wizzy reads on-chain data and never trades. NFA. DYOR. The runes are not financial advice."
        "</footer></main></body></html>"
    )


def omen_badge(omen: str | None) -> str:
    if not omen:
        return ""
    return f'<span class="omen" style="background:{OMEN_COLOR.get(omen, "#8ecae6")}">{esc(omen)}</span>'


def bear() -> str:
    return '<pre class="bear">' + esc("\n".join(mascot.POSES[(0, False)])) + "</pre>"


def landing(recent: list) -> str:
    items = (
        "".join(f'<li>{omen_badge(s.omen)} <a href="/s/{esc(s.slug)}">{esc(s.title)}</a></li>' for s in recent)
        or "<li class=dim>No scrolls yet.</li>"
    )
    body = (
        f"{bear()}<h1>Wizzy</h1><p>A small wizard bear who reads Solana tokens and wallets from on-chain data. "
        "Ask on Telegram or tag Wizzy on X with a $TICKER, a contract address or a wallet.</p>"
        f'<div class="card"><h2>Recent scrolls</h2><ul>{items}</ul></div>'
    )
    return layout("Wizzy reads the runes", body, desc="Cryptic, facts-only readings of Solana tokens and wallets.")


def scroll_page(s, *, base_url: str, full: bool, price: float | None, paywall_on: bool, familiar=None) -> str:
    og = f"{base_url.rstrip('/')}/og/{s.slug}.png"
    url = f"{base_url.rstrip('/')}/s/{s.slug}"
    chart = "".join(f'<img class="chart" src="{esc(c)}" alt="24h price chart">' for c in s.chart_urls[:1])
    if full:
        content = md(s.body_md)
    else:
        preview = section(s.body_md, "Overview")
        unlock = ""
        if paywall_on:
            unlock = (
                f'<p><a class="btn" href="/s/{esc(s.slug)}/full">Unlock the full scroll · ${price or 0:.2f} USDC</a></p>'
                '<p class="dim">Paid with x402 (USDC on Solana). Inner Circle members read every scroll free.</p>'
            )
        else:
            unlock = f'<p><a class="btn" href="/s/{esc(s.slug)}/full">Read the full scroll</a></p>'
        content = md(preview) + unlock
    fam = f'<p class="dim">Summoned with a {familiar.glyph} {esc(familiar.name)} familiar</p>' if familiar else ""
    body = (
        f"{omen_badge(s.omen)}<h1>{esc(s.title)}</h1>{fam}"
        f'<div class="card">{md(s.reading)}</div>{chart}<div class="card">{content}</div>'
    )
    return layout(s.title, body, og_image=og, url=url, desc=s.reading)
