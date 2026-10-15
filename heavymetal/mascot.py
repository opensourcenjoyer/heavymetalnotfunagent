"""ASCII mascot: a bear in a wizard hat, drawn in Braille dots.

It sits beside the startup banner, animates while the agent is thinking or running tools, and talks while the
reply streams. Frames are made by flipping individual Braille dots (eyes, mouth) of one base drawing, so every
frame has exactly the same size. Disable with ``HEAVYMETAL_MASCOT=0``.
"""

from __future__ import annotations

import os
import time

from rich.console import Console, RenderableType
from rich.table import Table
from rich.text import Text

# Converted from the reference drawing (50 columns x 18 rows, each character is a 2x4 dot cell).
ART = """\
      ⠐⣿⣦⡀
      ⢠⣿⣿⣿⣄
      ⠸⣿⣿⣿⣿⣦⡀   ⢀⣀⣤⣤⣶⣶⣾⣿⠆
       ⣿⣿⣿⣿⣿⣿⣶⣶⣿⣿⣿⣿⣿⣿⣟⣋⣀⡀
      ⢀⣿⣿⣿⣿⣿⣿⣿⡿⠿⠟⠋⠉⠉⠉⠉⠉⠉⠙⠛⠛⠛⠛⠛⠛⠶⠶⠶⠦⣤⣄
    ⣀⣴⣾⣿⣿⣿⠿⠛⢁⡀                      ⠈⣷⡀
 ⢀⣴⣿⣿⣿⣿⣿⠉ ⠛⠠⣄⣠⡶                      ⢸⡇
⣾⣿⣿⣿⣿⠿⠋⢻⡄⠘⠶⠾⠛⠉                       ⠸⣇
⠈⠉⠉⠉   ⠘⣧                             ⢿
        ⢻⡆                            ⠘⢷⡀
         ⠻⣆                            ⠛⣷⢶⡄
          ⠙⣧                      ⢠⡄⠸⣆⠘⠳⠞⣧⣤⡀
           ⢹⣇     ⣀⣀⣀⡀      ⢀⣠⣤⣤⣴⠶⣬⣟ ⢈⡀⣶ ⠘⣮
            ⢿⡀  ⢠⡞⠉⠉⠉⢻⡆    ⢰⡟⠁     ⠙⢷⡘⠗   ⠙⠓⠶⣦⣄⡀
           ⣀⣸⣇  ⢸⡇   ⠈⣧    ⢸⡇       ⢸⣇⡀      ⣤⣌⠉⠛⢶
         ⢀⣾⣭⣽⠿  ⢸⣇⡀   ⠘⣧   ⠸⣧⣤⣤⣤⡀    ⠉⠉⠛⠳⢦⣤⡐⢷⣌⣉⠛⣿⠛
         ⣿⣥⣴⠗⣠⣤⣄⣀⣉⣿   ⣀⡿ ⣀ ⢀ ⢶⣶⡾⠇         ⠈⠙⠷⠾⠿⠉⠉
          ⢿⣴⠞⠉ ⠈⠉⠉⠁  ⠸⣯⣤⡾⠙⠷⣬⣝⣷⠾⠇
"""

_BITS = ((0, 0, 0x01), (1, 0, 0x02), (2, 0, 0x04), (0, 1, 0x08), (1, 1, 0x10), (2, 1, 0x20), (3, 0, 0x40), (3, 1, 0x80))

_ROWS = ART.rstrip("\n").split("\n")
WIDTH = max(len(r) for r in _ROWS)
HEIGHT = len(_ROWS)
DOT_W, DOT_H = WIDTH * 2, HEIGHT * 4

Dots = frozenset[tuple[int, int]]  # (x, y) dot coordinates


def decode(rows: list[str]) -> Dots:
    dots = set()
    for r, line in enumerate(rows):
        for c, ch in enumerate(line):
            v = ord(ch) - 0x2800 if ch != " " else 0
            for dy, dx, bit in _BITS:
                if v & bit:
                    dots.add((c * 2 + dx, r * 4 + dy))
    return frozenset(dots)


def encode(dots: Dots) -> list[str]:
    rows = []
    for r in range(HEIGHT):
        line = []
        for c in range(WIDTH):
            v = sum(bit for dy, dx, bit in _BITS if (c * 2 + dx, r * 4 + dy) in dots)
            line.append(chr(0x2800 + v) if v else " ")
        rows.append("".join(line))
    return rows


def _rect(x0: int, x1: int, y0: int, y1: int) -> set[tuple[int, int]]:
    return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}


BASE = decode(_ROWS)

# Face features, in dot coordinates (see the reference drawing: two eyes, a nose dot, a wide smile).
LEFT_EYE = BASE & _rect(20, 21, 24, 25)
RIGHT_EYE = BASE & _rect(25, 26, 22, 23)
NOSE = BASE & _rect(23, 24, 26, 26)
SMILE = (BASE & _rect(19, 29, 25, 31)) - LEFT_EYE - RIGHT_EYE - NOSE - _rect(15, 18, 25, 31)

_CLOSED_EYES = _rect(19, 22, 25, 25) | _rect(24, 27, 23, 23)


def _face(mouth: int, blink: bool) -> Dots:
    """mouth: 0 smile, 1 half open, 2 open."""
    d = set(BASE)
    if blink:
        d -= LEFT_EYE | RIGHT_EYE
        d |= _CLOSED_EYES
    for shift in range(1, mouth + 1):  # drop the smile down to open the mouth
        d |= {(x, y + shift) for x, y in SMILE}
    return frozenset(d)


def _solid(dots: Dots) -> Dots:
    """Morphological opening: keeps only filled areas (the hat), drops outlines."""
    core = {(x, y) for x, y in dots if all((x + i, y + j) in dots for i in (-1, 0, 1) for j in (-1, 0, 1))}
    return frozenset({(x + i, y + j) for x, y in core for i in (-1, 0, 1) for j in (-1, 0, 1)} & dots)


_HAT = frozenset(d for d in _solid(BASE) if d[1] < DOT_H // 2)  # the hat is the only solid area up top
HAT_CELLS = frozenset(
    (c, r)
    for r in range(HEIGHT)
    for c in range(WIDTH)
    if sum((c * 2 + dx, r * 4 + dy) in _HAT for dy, dx, _ in _BITS) >= 4
)

# Precomputed rows for every (mouth, blink) pose.
POSES = {(m, b): encode(_face(m, b)) for m in (0, 1, 2) for b in (False, True)}

# Sparkles float in the empty space around the hat tip: (column, row, char) per phase.
SPARKLES = (
    ((4, 0, "✦"), (10, 1, "·")),
    ((2, 1, "·"), (11, 0, "✧")),
    ((5, 2, "✧"), (9, 0, "·")),
    ((1, 0, "·"), (12, 1, "✦")),
    ((3, 2, "✦"), (10, 0, "·")),
    ((0, 1, "✧"), (11, 2, "·")),
)
SPARKLE_STYLE = "bold yellow"
HAT_STYLE = "bold magenta"

FPS = 8  # animation ticks per second
MOUTH_CYCLE = (0, 1, 2, 1)
BLINK_EVERY = 3.5  # seconds between blinks
BLINK_FOR = 0.18


def enabled(console: Console | None = None) -> bool:
    if os.environ.get("HEAVYMETAL_MASCOT", "1").lower() in ("0", "false", "no", "off"):
        return False
    return console is None or (console.is_terminal and console.width >= WIDTH + 40)


def render(mouth: int = 0, blink: bool = False, sparkle: int | None = None) -> Text:
    """Style one frame: hat magenta, sparkles yellow, body in the default colour."""
    rows = [list(r) for r in POSES[(mouth, blink)]]
    sparks = {}
    if sparkle is not None:
        for c, r, ch in SPARKLES[sparkle % len(SPARKLES)]:
            if rows[r][c] == " ":
                rows[r][c] = ch
                sparks[(c, r)] = True
    out = Text(no_wrap=True)
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            style = SPARKLE_STYLE if (c, r) in sparks else HAT_STYLE if (c, r) in HAT_CELLS else ""
            out.append(ch, style)
        if r < HEIGHT - 1:
            out.append("\n")
    return out


def _tick(now: float | None) -> tuple[int, bool]:
    now = time.monotonic() if now is None else now
    return int(now * FPS), (now % BLINK_EVERY) < BLINK_FOR


def idle() -> Text:
    return render()


def waiting(now: float | None = None) -> Text:
    """Thinking pose: mouth shut, sparkles orbit the hat, occasional blink."""
    tick, blink = _tick(now)
    return render(0, blink, tick // 2)


def talking(index: int | None = None) -> Text:
    """Talking pose. ``index`` picks a frame explicitly; by default it advances with wall-clock time."""
    if index is None:
        tick, blink = _tick(None)
    else:
        tick, blink = index, False
    return render(MOUTH_CYCLE[tick % len(MOUTH_CYCLE)], blink, tick // 2)


def beside(frame: Text, body: RenderableType) -> Table:
    """Mascot on the left, ``body`` on the right."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(width=WIDTH, no_wrap=True)
    grid.add_column(ratio=1)
    grid.add_row(frame, body)
    return grid
