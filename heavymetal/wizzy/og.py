"""Open Graph images for scrolls (1200x630 PNG): the bear, the omen colour, the title. Never the paid body."""

from __future__ import annotations

import io
from functools import lru_cache
from importlib import resources

from PIL import Image, ImageDraw, ImageFont, ImageOps

from heavymetal.wizzy.charts import OMEN_COLOR

W, H = 1200, 630
BG = (26, 20, 38)
INK = (233, 228, 240)


@lru_cache(maxsize=1)
def bear() -> Image.Image:
    with resources.files("heavymetal.wizzy").joinpath("assets/wizzy.png").open("rb") as f:
        img = Image.open(f).convert("L")
        img.load()
    # Line drawing on white -> light ink on transparent, to sit on the dark card.
    alpha = ImageOps.invert(img).point(lambda v: 255 if v > 90 else 0)
    out = Image.new("RGBA", img.size, INK + (0,))
    out.putalpha(alpha)
    return out


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int, max_lines: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and " ".join(lines) != text:
        lines[-1] = lines[-1].rstrip(".,;: ") + "…"
    return lines


def render(title: str, omen: str | None, subtitle: str = "") -> bytes:
    img = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(img)
    color = OMEN_COLOR.get(omen, OMEN_COLOR[None])
    d.rectangle([0, 0, W, 14], fill=color)
    b = bear()
    scale = 430 / b.height
    bb = b.resize((int(b.width * scale), 430))
    img.alpha_composite(bb, (W - bb.width - 40, H - bb.height - 40))
    y = 70
    if omen:
        d.text((60, y), omen.upper(), font=_font(44), fill=color)
        y += 70
    for line in _wrap(d, title or "A Wizzy scroll", _font(64), W - bb.width - 140, 3):
        d.text((60, y), line, font=_font(64), fill=INK)
        y += 80
    if subtitle:
        for line in _wrap(d, subtitle, _font(32), W - bb.width - 140, 3):
            d.text((60, y + 10), line, font=_font(32), fill=(184, 176, 200))
            y += 44
    d.text((60, H - 70), "Wizzy reads the runes · NFA · DYOR", font=_font(28), fill=(150, 140, 170))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def render_tarot(title: str, cards: list[dict]) -> bytes:
    """Three tarot cards side by side with their glyphs and names."""
    img = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill=(199, 125, 255))
    d.text((60, 40), title or "Three cards for a wallet", font=_font(46), fill=INK)
    cw, ch, gap = 300, 420, 50
    x0 = (W - (3 * cw + 2 * gap)) // 2
    for i, c in enumerate(cards[:3]):
        x = x0 + i * (cw + gap)
        d.rounded_rectangle([x, 130, x + cw, 130 + ch], radius=22, fill=(36, 28, 53), outline=(199, 125, 255), width=4)
        d.text((x + cw // 2, 170), (c.get("slot") or "").upper(), font=_font(26), fill=(184, 176, 200), anchor="mm")
        for j, line in enumerate(_wrap(d, c.get("name") or "?", _font(40), cw - 40, 2)):
            d.text((x + cw // 2, 330 + j * 50), line, font=_font(40), fill=INK, anchor="mm")
    d.text((60, H - 50), "Wizzy reads the runes · NFA · DYOR", font=_font(26), fill=(150, 140, 170))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()
