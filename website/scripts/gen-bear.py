"""Export the Braille bear from heavymetal/mascot.py to src/lib/bear/data.json (run from website/).

    ../.venv/bin/python scripts/gen-bear.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from heavymetal import mascot  # noqa: E402

out = {
    "width": mascot.WIDTH,
    "height": mascot.HEIGHT,
    "poses": {f"{m}{int(b)}": rows for (m, b), rows in mascot.POSES.items()},
    "hatCells": sorted(mascot.HAT_CELLS),
    "face": sorted(mascot.LEFT_EYE | mascot.RIGHT_EYE | mascot.NOSE | mascot.SMILE),
    "sparkles": [[list(s) for s in phase] for phase in mascot.SPARKLES],
    "mouthCycle": list(mascot.MOUTH_CYCLE),
    "fps": mascot.FPS,
    "blinkEvery": mascot.BLINK_EVERY,
    "blinkFor": mascot.BLINK_FOR,
}
dst = Path("src/lib/bear/data.json")
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(json.dumps(out, ensure_ascii=False) + "\n")
# Favicon: the head and hat, one circle per Braille dot, hat in the primary colour.
hat = mascot._HAT
crop = [(x, y) for x, y in mascot.BASE if x < 40 and y < 44]
circles = "".join(
    f'<circle cx="{x + 0.5}" cy="{y + 0.5}" r="0.42" fill="{"#d968ff" if (x, y) in hat else "#16131c"}"/>' for x, y in crop
)
Path("src/app/icon.svg").write_text(
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-2 -2 44 48"><rect x="-2" y="-2" width="44" height="48" fill="#f4f1ea"/>{circles}</svg>\n'
)
print(f"wrote {dst}: {mascot.WIDTH}x{mascot.HEIGHT}, {len(mascot.HAT_CELLS)} hat cells")
